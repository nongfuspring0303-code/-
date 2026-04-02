#!/usr/bin/env python3
"""
AI signal adapter for B1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus
from narrative_state_recognizer import NarrativeStateRecognizer


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


class AISignalAdapter(EDTModule):
    """Map AI intel output into A0/A-1/A1/A1.5/A0.5 factors."""

    def __init__(self, config_path: Optional[str] = None):
        cfg = config_path or _default_config_path()
        super().__init__("AISignalAdapter", "1.0.0", cfg)
        self.narrative = NarrativeStateRecognizer(cfg)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["trace_id", "event_id", "evidence_score", "consistency_score", "freshness_score", "confidence"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    @staticmethod
    def _clamp(v: Any) -> float:
        return max(0.0, min(100.0, float(v)))

    def _resolve_mapping(self, requested_version: str | None) -> tuple[str, Dict[str, str]]:
        params = self._get_config("modules.AISignalAdapter.params", {})
        active = str(params.get("active_mapping_version", "factor_map_v1"))
        mappings = params.get("mapping_versions", {})
        rollback = bool(params.get("allow_version_rollback", True))

        candidate = requested_version or active
        if candidate in mappings:
            return candidate, dict(mappings[candidate])
        if rollback and active in mappings:
            return active, dict(mappings[active])
        default_map = {
            "A0": "evidence_score",
            "A-1": "consistency_score",
            "A1": "freshness_score",
            "A1.5": "confidence",
            "A0.5": "counter_signal_penalty",
        }
        return active, default_map

    def _extract_factor(self, mapping_field: str, raw: Dict[str, Any]) -> float:
        if mapping_field in raw:
            return self._clamp(raw[mapping_field])
        if mapping_field == "counter_signal_penalty":
            confidence = self._clamp(raw.get("confidence", 0))
            consistency = self._clamp(raw.get("consistency_score", 0))
            return self._clamp((100.0 - confidence) * 0.6 + (100.0 - consistency) * 0.4)
        return 0.0

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data

        requested_version = raw.get("mapping_version")
        mapping_version, mapping = self._resolve_mapping(str(requested_version) if requested_version else None)

        narrative_out = self.narrative.run(raw)
        if narrative_out.status != ModuleStatus.SUCCESS:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "NARRATIVE_STATE_ERROR", "message": "NarrativeStateRecognizer failed."}],
            )

        factors = {
            "A0": self._extract_factor(mapping.get("A0", "evidence_score"), raw),
            "A-1": self._extract_factor(mapping.get("A-1", "consistency_score"), raw),
            "A1": self._extract_factor(mapping.get("A1", "freshness_score"), raw),
            "A1.5": self._extract_factor(mapping.get("A1.5", "confidence"), raw),
            "A0.5": self._extract_factor(mapping.get("A0.5", "counter_signal_penalty"), raw),
        }

        confidence = self._clamp(raw.get("confidence", 0))
        review_threshold = float(self._get_config("modules.AISignalAdapter.params.review_threshold", 60))
        ai_review_required = bool(confidence < review_threshold)
        ai_review_passed = not ai_review_required

        narrative_state = narrative_out.data["narrative_state"]
        if narrative_state in {"initial", "continuation"}:
            base_direction = "long"
        elif narrative_state == "decay":
            base_direction = "neutral"
        else:
            base_direction = "neutral"

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "trace_id": raw["trace_id"],
                "event_id": raw["event_id"],
                "A0": round(factors["A0"], 2),
                "A-1": round(factors["A-1"], 2),
                "A1": round(factors["A1"], 2),
                "A1.5": round(factors["A1.5"], 2),
                "A0.5": round(factors["A0.5"], 2),
                "base_direction": base_direction,
                "narrative_state": narrative_state,
                "mapping_version": mapping_version,
                "schema_version": raw.get("schema_version", "ai_factor_map_v1"),
                "producer": raw.get("producer", "member-b"),
                "generated_at": raw.get("generated_at", datetime.now(timezone.utc).isoformat()),
                "model_id": raw.get("model_id", "unknown"),
                "prompt_version": raw.get("prompt_version", "unknown"),
                "temperature": raw.get("temperature", 0.0),
                "timeout_ms": raw.get("timeout_ms", 10000),
                "ai_review_required": ai_review_required,
                "ai_review_passed": ai_review_passed,
                "reasoning": [
                    f"Mapping version={mapping_version}",
                    f"Narrative state={narrative_state}",
                    f"review_required={ai_review_required}",
                ],
            },
        )

