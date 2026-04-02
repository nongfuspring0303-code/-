#!/usr/bin/env python3
"""
Narrative state recognizer for B4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


class NarrativeStateRecognizer(EDTModule):
    """Infer and normalize narrative state for AI-assisted strategy flow."""

    VALID_STATES = {"initial", "continuation", "decay", "invalid"}

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("NarrativeStateRecognizer", "1.0.0", config_path or _default_config_path())

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["trace_id", "event_id", "evidence_score", "consistency_score", "freshness_score", "confidence"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    @staticmethod
    def _norm_state(value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in NarrativeStateRecognizer.VALID_STATES else ""

    @staticmethod
    def _clamp(v: Any) -> float:
        return max(0.0, min(100.0, float(v)))

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        previous_state = self._norm_state(raw.get("previous_narrative_state"))
        upstream_state = self._norm_state(raw.get("narrative_state"))
        contradicted = bool(raw.get("contradicted_by_fact", False))

        evidence = self._clamp(raw["evidence_score"])
        consistency = self._clamp(raw["consistency_score"])
        freshness = self._clamp(raw["freshness_score"])
        confidence = self._clamp(raw["confidence"])

        if contradicted:
            state = "invalid"
            reason = "Contradicted by facts."
        elif upstream_state:
            state = upstream_state
            reason = "Trusted upstream narrative_state."
        elif confidence < 30:
            state = "invalid"
            reason = "Confidence below invalid threshold."
        elif evidence < 40 or consistency < 40 or freshness < 35:
            state = "decay"
            reason = "Signal quality decayed."
        elif previous_state in {"initial", "continuation"} and evidence >= 55 and consistency >= 55:
            state = "continuation"
            reason = "Continuation from previous valid narrative state."
        elif evidence >= 70 and consistency >= 65 and freshness >= 65:
            state = "initial"
            reason = "Strong fresh evidence."
        else:
            state = "continuation"
            reason = "Default continuation."

        transition_ok = True
        if previous_state == "invalid" and state in {"initial", "continuation"} and confidence < 70:
            transition_ok = False
            state = "invalid"
            reason = "Blocked transition from invalid without enough confidence."

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "trace_id": raw["trace_id"],
                "event_id": raw["event_id"],
                "previous_state": previous_state or None,
                "narrative_state": state,
                "transition_valid": transition_ok,
                "reasoning": reason,
            },
        )

