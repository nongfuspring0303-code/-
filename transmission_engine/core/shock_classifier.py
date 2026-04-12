#!/usr/bin/env python3
"""Shock classifier for Phase 4 (TM-1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class ShockProfile:
    primary: List[str]
    secondary: List[str]
    narrative: List[str]

    def to_dict(self) -> Dict[str, List[str]]:
        return {
            "primary": list(self.primary),
            "secondary": list(self.secondary),
            "narrative": list(self.narrative),
        }


class ShockClassifier:
    """Classify event shocks and event types using config mappings."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        base = Path(__file__).resolve().parents[2]
        self.config_dir = config_dir or base / "configs"
        self.event_type_map = self._load_yaml(self.config_dir / "event_type_lv2_mapping.yaml")
        self.event_to_shock = self._load_yaml(self.config_dir / "event_to_shock.yaml")

    def classify(
        self,
        category: str,
        headline: str,
        summary: str,
        severity: str | int | None = None,
    ) -> Dict[str, Any]:
        text = self._normalize_text(headline, summary)
        event_type = self._match_event_type(category, text)
        shock_profile = self._match_shock_profile(event_type["event_type_lv2"])

        classification_confidence = 55
        if event_type.get("matched_keywords"):
            classification_confidence = 75

        market_impact_confidence = self._severity_score(severity)

        return {
            "event_type_lv1": event_type["event_type_lv1"],
            "event_type_lv2": event_type["event_type_lv2"],
            "shock_profile": shock_profile.to_dict(),
            "classification_confidence": classification_confidence,
            "market_impact_confidence": market_impact_confidence,
        }

    def _match_event_type(self, category: str, text: str) -> Dict[str, Any]:
        mappings = self.event_type_map.get("mappings", []) or []
        best_match = None
        for item in mappings:
            keywords = item.get("keywords", []) or []
            if not isinstance(keywords, list):
                continue
            if self._match_keywords(text, keywords):
                best_match = item
                break

        if best_match:
            return {
                "event_type_lv1": best_match.get("lv1", "macro"),
                "event_type_lv2": best_match.get("lv2", "macro_generic"),
                "matched_keywords": True,
            }

        defaults = self.event_type_map.get("category_defaults", {}) or {}
        fallback = defaults.get(str(category).upper(), {})
        return {
            "event_type_lv1": fallback.get("lv1", "macro"),
            "event_type_lv2": fallback.get("lv2", "macro_generic"),
            "matched_keywords": False,
        }

    def _match_shock_profile(self, event_type_lv2: str) -> ShockProfile:
        mappings = self.event_to_shock.get("mappings", {}) or {}
        profile = mappings.get(event_type_lv2, {}) or {}
        defaults = self.event_to_shock.get("defaults", {}) or {}

        return ShockProfile(
            primary=list(profile.get("primary", defaults.get("primary", ["risk_off"]))),
            secondary=list(profile.get("secondary", defaults.get("secondary", []))),
            narrative=list(profile.get("narrative", defaults.get("narrative", []))),
        )

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _normalize_text(*parts: Any) -> str:
        return " ".join(str(part or "").lower() for part in parts).strip()

    @staticmethod
    def _match_keywords(text: str, keywords: List[str]) -> bool:
        lower = text.lower()
        for kw in keywords:
            needle = str(kw).strip().lower()
            if not needle:
                continue
            if needle in lower:
                return True
        return False

    @staticmethod
    def _severity_score(severity: str | int | None) -> int:
        if severity is None:
            return 60
        if isinstance(severity, int):
            return max(40, min(95, 40 + severity * 15))
        key = str(severity).upper()
        mapping = {
            "E1": 50,
            "E2": 65,
            "E3": 80,
            "E4": 90,
        }
        return mapping.get(key, 60)
