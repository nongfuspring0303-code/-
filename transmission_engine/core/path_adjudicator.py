#!/usr/bin/env python3
"""
Member B path adjudication layer.

This module ranks transmission paths, marks mixed_regime when dominance gaps
are too small, and applies the narrative guard without making any state-machine
or trade-admission decision.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.config_center import ConfigCenter
from scripts.edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class PathAdjudicator(EDTModule):
    """Rank and adjudicate transmission paths."""

    PATH_PRIORITY = {"fundamental": 0, "asset_pricing": 1, "narrative": 2}

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("PathAdjudicator", "1.0.0", config_path)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.gate_policy_path = self.repo_root / "configs" / "gate_policy.yaml"
        self.metric_dictionary_path = self.repo_root / "configs" / "metric_dictionary.yaml"
        self.config_center = ConfigCenter(config_path=config_path)
        self.config_center.register("gate_policy", self.gate_policy_path)
        self.config_center.register("metric_dictionary", self.metric_dictionary_path)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        paths = input_data.get("transmission_paths")
        if paths is None:
            return False, "Missing required field: transmission_paths"
        if not isinstance(paths, list):
            return False, "transmission_paths must be a list"
        return True, None

    def _gate_policy(self) -> Dict[str, Any]:
        policy = self.config_center.get_registered("gate_policy", {})
        return policy if isinstance(policy, dict) else {}

    def _metric_dictionary(self) -> Dict[str, Any]:
        metrics = self.config_center.get_registered("metric_dictionary", {})
        return metrics if isinstance(metrics, dict) else {}

    @staticmethod
    def _round(value: Any, precision: int) -> float:
        try:
            return round(float(value), precision)
        except (TypeError, ValueError):
            return round(0.0, precision)

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _precision(self) -> int:
        metrics = self._metric_dictionary()
        standards = metrics.get("standards", {}) if isinstance(metrics, dict) else {}
        return int(standards.get("default_rounding_decimals", 2))

    def _path_score(self, path: Dict[str, Any]) -> float:
        return self._round(self._as_float(path.get("confidence", path.get("score", 0.0))), self._precision())

    def _normalize_path(self, path: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "path_id": str(path.get("path_id", "")),
            "path_name": str(path.get("path_name") or path.get("name") or path.get("path_id") or ""),
            "path_type": str(path.get("path_type", "")),
            "horizon": str(path.get("horizon", "1-5D")),
            "persistence": str(path.get("persistence", "medium")),
            "confidence": self._path_score(path),
        }

    def _rank_paths(self, paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        precision = self._precision()

        def sort_key(item: Dict[str, Any]) -> tuple[float, int, str]:
            score = self._round(self._as_float(item.get("confidence", item.get("score", 0.0))), precision)
            priority = self.PATH_PRIORITY.get(str(item.get("path_type", "")), 99)
            return (-score, priority, str(item.get("path_name") or item.get("path_id") or ""))

        return sorted(paths, key=sort_key)

    def _narrative_guard(self, ranked: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], bool, bool]:
        if not ranked:
            return [], False, False

        top = ranked[0]
        top_type = str(top.get("path_type", ""))
        if top_type != "narrative":
            return ranked, False, False

        fundamental_best = max(
            [self._as_float(p.get("confidence", p.get("score", 0.0))) for p in ranked if str(p.get("path_type", "")) == "fundamental"],
            default=0.0,
        )
        asset_best = max(
            [self._as_float(p.get("confidence", p.get("score", 0.0))) for p in ranked if str(p.get("path_type", "")) == "asset_pricing"],
            default=0.0,
        )
        if fundamental_best >= 50.0 or asset_best >= 50.0:
            return ranked, False, False

        non_narrative = [p for p in ranked if str(p.get("path_type", "")) != "narrative"]
        if non_narrative:
            return self._rank_paths(non_narrative) + [p for p in ranked if str(p.get("path_type", "")) == "narrative"], True, True

        return ranked, True, False

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        precision = self._precision()
        min_gap = float(self._gate_policy().get("path_dominance", {}).get("min_gap", 12.0))

        normalized = [self._normalize_path(path) for path in raw.get("transmission_paths", []) if isinstance(path, dict)]
        ranked = self._rank_paths(normalized)
        ranked, narrative_guarded, reordered = self._narrative_guard(ranked)

        top1 = ranked[0] if ranked else None
        top2 = ranked[1] if len(ranked) > 1 else None
        top1_score = self._as_float(top1.get("confidence", 0.0)) if top1 else 0.0
        top2_score = self._as_float(top2.get("confidence", 0.0)) if top2 else 0.0
        mixed_regime = bool(top2 and (top1_score - top2_score) < min_gap)

        dominant = top1 or {}
        if narrative_guarded and reordered:
            dominant = ranked[0]
        elif narrative_guarded and not reordered and dominant:
            # No non-narrative alternative exists; keep the narrative path but
            # mark the guard state for downstream consumers.
            pass

        dominant_path = {
            "name": dominant.get("path_name", dominant.get("path_id", "")),
            "confidence": self._round(self._as_float(dominant.get("confidence", 0.0)), precision),
            "horizon": dominant.get("horizon", "1-5D"),
            "path_type": dominant.get("path_type", ""),
        }

        remaining = [path for path in ranked if path.get("path_id") != dominant.get("path_id")]
        competing_paths = remaining[:1]
        suppressed_paths = remaining[1:]

        if narrative_guarded and top1:
            narrative_top = {
                "path_id": top1.get("path_id", ""),
                "name": top1.get("path_name", top1.get("path_id", "")),
                "confidence": self._round(top1_score, precision),
                "horizon": top1.get("horizon", "1-5D"),
                "path_type": top1.get("path_type", ""),
                "reason": "narrative_guard",
            }
            if all(item.get("path_id") != narrative_top["path_id"] for item in suppressed_paths) and narrative_top["path_id"] != dominant.get("path_id"):
                suppressed_paths = [narrative_top] + suppressed_paths

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "dominant_path": dominant_path,
                "competing_paths": competing_paths,
                "suppressed_paths": suppressed_paths,
                "mixed_regime": mixed_regime,
            },
            metadata={
                "path_count": len(ranked),
                "top1_score": self._round(top1_score, precision),
                "top2_score": self._round(top2_score, precision),
                "dominance_gap": self._round(top1_score - top2_score, precision),
                "narrative_guarded": narrative_guarded,
            },
        )
