#!/usr/bin/env python3
"""Factor vectorizer for Phase 4 (TM-2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class FactorVectorizer:
    """Generate raw macro factor vectors based on templates and coefficients."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        base = Path(__file__).resolve().parents[2]
        self.config_dir = config_dir or base / "configs"
        self.config = self._load_yaml(self.config_dir / "factor_templates.yaml")

    def vectorize(
        self,
        event_type_lv2: str,
        severity: str | int | None = None,
        lifecycle_state: str | None = None,
        novelty_score: float | None = None,
        fatigue_final: float | None = None,
    ) -> Dict[str, float]:
        factors = self.config.get("factors", []) or []
        templates = self.config.get("templates", {}) or {}
        defaults = self.config.get("defaults", {}) or {}

        base_vector = templates.get(event_type_lv2, defaults)
        raw_vector: Dict[str, float] = {}

        severity_coeff = self._severity_coeff(severity)
        lifecycle_coeff = self._lifecycle_coeff(lifecycle_state)
        novelty_coeff = self._novelty_coeff(novelty_score)
        fatigue_coeff = self._fatigue_coeff(fatigue_final)

        multiplier = severity_coeff * lifecycle_coeff * novelty_coeff * fatigue_coeff

        for factor in factors:
            base_value = float(base_vector.get(factor, 0.0))
            value = self._clamp(base_value * multiplier)
            raw_vector[factor] = round(value, 2)

        return raw_vector

    def _severity_coeff(self, severity: str | int | None) -> float:
        coeffs = self.config.get("coefficients", {}).get("severity", {}) or {}
        if isinstance(severity, int):
            if severity <= 1:
                return float(coeffs.get("E1", 0.4))
            if severity == 2:
                return float(coeffs.get("E2", 0.7))
            if severity == 3:
                return float(coeffs.get("E3", 1.0))
            return float(coeffs.get("E4", 1.35))
        key = str(severity or "E2").upper()
        return float(coeffs.get(key, 0.7))

    def _lifecycle_coeff(self, lifecycle_state: str | None) -> float:
        coeffs = self.config.get("coefficients", {}).get("lifecycle", {}) or {}
        key = str(lifecycle_state or "Active")
        return float(coeffs.get(key, 1.0))

    @staticmethod
    def _novelty_coeff(novelty_score: float | None) -> float:
        if novelty_score is None:
            return 1.0
        return max(0.6, min(1.2, float(novelty_score)))

    @staticmethod
    def _fatigue_coeff(fatigue_final: float | None) -> float:
        if fatigue_final is None:
            return 1.0
        return max(0.3, 1 - float(fatigue_final) / 180.0)

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-100.0, min(100.0, value))
