#!/usr/bin/env python3
"""
ExecutionSuggestionBuilder (PR112)

Analysis-layer advisory-only suggestion generator.
Hard boundary:
- Output is for human review only.
- Must not be consumed by Gate/final_action/execution path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class ExecutionSuggestionBuilder(EDTModule):
    """Build advisory execution suggestions from analysis signals."""

    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            default_policy = Path(__file__).resolve().parent.parent / "configs" / "execution_suggestion_policy.yaml"
            config_path = str(default_policy) if default_policy.exists() else None
        super().__init__("ExecutionSuggestionBuilder", "1.0.0", config_path)
        self._load_policy()

    def _load_policy(self) -> None:
        policy = self.config if isinstance(self.config, dict) else {}
        self.thresholds = policy.get(
            "thresholds",
            {
                "breakout_min_score": 80,
                "low_buy_min_score": 65,
                "watch_min_score": 40,
                "kill_switch_fatigue_min": 90,
                "reduce_only_fatigue_min": 75,
            },
        )
        self.position_bands = policy.get(
            "position_bands",
            {
                "breakout": {"min": 0.30, "max": 0.60, "mode": "range"},
                "low_buy": {"min": 0.15, "max": 0.35, "mode": "range"},
                "watch": {"min": 0.00, "max": 0.00, "mode": "zero"},
                "avoid": {"min": 0.00, "max": 0.00, "mode": "zero"},
                "intraday_only": {"min": 0.10, "max": 0.25, "mode": "range"},
            },
        )

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        score = self._to_float(raw.get("score"), 0.0)
        fatigue_score = self._to_float(raw.get("fatigue_score"), 0.0)
        has_opportunity = bool(raw.get("has_opportunity", False))
        market_validated = bool(raw.get("market_validated", False))
        lifecycle_state = str(raw.get("lifecycle_state") or "")
        stale_event = raw.get("stale_event") if isinstance(raw.get("stale_event"), dict) else {}
        is_stale = bool(stale_event.get("is_stale", False))

        breakout_min = self._to_float(self.thresholds.get("breakout_min_score"), 80)
        low_buy_min = self._to_float(self.thresholds.get("low_buy_min_score"), 65)
        watch_min = self._to_float(self.thresholds.get("watch_min_score"), 40)
        kill_switch_min = self._to_float(self.thresholds.get("kill_switch_fatigue_min"), 90)
        reduce_only_min = self._to_float(self.thresholds.get("reduce_only_fatigue_min"), 75)

        if (is_stale and not market_validated) or score < watch_min or not has_opportunity:
            trade_type = "avoid"
        elif score >= breakout_min and market_validated:
            trade_type = "breakout"
        elif score >= low_buy_min:
            trade_type = "low_buy"
        else:
            trade_type = "watch"

        if is_stale and not market_validated:
            risk_switch = "no_trade"
        elif fatigue_score >= kill_switch_min:
            risk_switch = "kill_switch"
        elif fatigue_score >= reduce_only_min:
            risk_switch = "reduce_only"
        else:
            risk_switch = "normal"

        if risk_switch in {"no_trade", "kill_switch"}:
            trade_type = "avoid"

        band = self.position_bands.get(trade_type, {"min": 0.0, "max": 0.0, "mode": "zero"})
        if risk_switch == "reduce_only":
            pct_min = max(0.0, self._to_float(band.get("min"), 0.0) * 0.5)
            pct_max = max(pct_min, self._to_float(band.get("max"), 0.0) * 0.5)
        elif risk_switch in {"no_trade", "kill_switch"}:
            pct_min = 0.0
            pct_max = 0.0
        else:
            pct_min = max(0.0, self._to_float(band.get("min"), 0.0))
            pct_max = max(pct_min, self._to_float(band.get("max"), 0.0))

        if trade_type == "breakout":
            entry_window = "breakout_confirm"
            entry_trigger = "price breaks key level with volume confirmation"
        elif trade_type == "low_buy":
            entry_window = "pullback_confirm"
            entry_trigger = "pullback holds support and confirms rebound"
        elif trade_type == "watch":
            entry_window = "next_day_watch"
            entry_trigger = "wait for stronger validation before entry"
        else:
            entry_window = "none"
            entry_trigger = "no trade setup"

        if risk_switch in {"no_trade", "kill_switch"}:
            stop_kind = "event_stop"
            stop_rule = "do not enter until risk switch returns to normal"
        elif trade_type in {"breakout", "low_buy"}:
            stop_kind = "price_stop"
            stop_rule = "exit if price invalidates setup support/breakout level"
        else:
            stop_kind = "time_stop"
            stop_rule = "no action; re-evaluate on next observation window"

        if lifecycle_state in {"Active", "Continuation"} and market_validated and risk_switch == "normal":
            overnight_allowed = "conditional"
        elif risk_switch in {"no_trade", "kill_switch"}:
            overnight_allowed = "false"
        else:
            overnight_allowed = "false"

        data = {
            "trade_type": trade_type,
            "position_sizing": {
                "mode": str(band.get("mode", "zero")),
                "suggested_pct_min": round(pct_min, 4),
                "suggested_pct_max": round(pct_max, 4),
                "note": "advisory_only_human_review",
            },
            "entry_timing": {
                "window": entry_window,
                "trigger": entry_trigger,
            },
            "risk_switch": risk_switch,
            "stop_condition": {
                "kind": stop_kind,
                "rule": stop_rule,
            },
            "overnight_allowed": overnight_allowed,
        }
        return ModuleOutput(status=ModuleStatus.SUCCESS, data=data)

