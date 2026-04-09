#!/usr/bin/env python3
"""Feature-flagged semantic analyzer with deterministic fallback."""

from __future__ import annotations

from typing import Any, Dict

from config_center import ConfigCenter


class SemanticAnalyzer:
    def __init__(self, config_path: str | None = None):
        self.config = ConfigCenter(config_path=config_path)

    def _enabled(self) -> bool:
        runtime = self.config.data.get("runtime", {}) if isinstance(self.config.data, dict) else {}
        semantic = runtime.get("semantic", {}) if isinstance(runtime, dict) else {}
        return bool(semantic.get("enabled", False))

    def _min_confidence(self) -> int:
        runtime = self.config.data.get("runtime", {}) if isinstance(self.config.data, dict) else {}
        semantic = runtime.get("semantic", {}) if isinstance(runtime, dict) else {}
        value = semantic.get("min_confidence", 70)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 70
        return max(0, min(100, parsed))

    def analyze(self, headline: str, raw_text: str = "") -> Dict[str, Any]:
        if not self._enabled():
            return {
                "event_type": "unknown",
                "sentiment": "neutral",
                "confidence": 0,
                "recommended_chain": "",
                "fallback_reason": "semantic_disabled",
            }

        text = f"{headline} {raw_text}".lower()

        if any(k in text for k in ["trade meeting", "trade talks", "贸易会议", "贸易谈判", "谈判"]):
            out = {
                "event_type": "trade_talks",
                "sentiment": "neutral",
                "confidence": 80,
                "recommended_chain": "trade_talks_chain",
            }
        elif any(k in text for k in ["tariff", "trade war", "关税", "贸易战"]):
            out = {
                "event_type": "tariff",
                "sentiment": "negative",
                "confidence": 82,
                "recommended_chain": "tariff_chain",
            }
        else:
            out = {
                "event_type": "unknown",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
            }

        if out["confidence"] < self._min_confidence():
            out["fallback_reason"] = "confidence_below_threshold"
        return out
