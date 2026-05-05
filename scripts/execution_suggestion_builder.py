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

    @staticmethod
    def _as_float(value: Any, name: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"execution_suggestion policy invalid numeric value for {name}")

    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            default_policy = Path(__file__).resolve().parent.parent / "configs" / "execution_suggestion_policy.yaml"
            if not default_policy.exists():
                raise FileNotFoundError(f"execution_suggestion policy missing: {default_policy}")
            config_path = str(default_policy)
        else:
            p = Path(config_path)
            if not p.exists():
                raise FileNotFoundError(f"execution_suggestion policy missing: {p}")
        super().__init__("ExecutionSuggestionBuilder", "1.0.0", config_path)
        self._load_policy()

    def _load_policy(self) -> None:
        policy = self.config if isinstance(self.config, dict) else {}
        thresholds = policy.get("thresholds")
        position_bands = policy.get("position_bands")
        if not isinstance(thresholds, dict):
            raise ValueError("execution_suggestion policy missing thresholds")
        if not isinstance(position_bands, dict):
            raise ValueError("execution_suggestion policy missing position_bands")

        required_thresholds = {
            "breakout_min_score",
            "low_buy_min_score",
            "watch_min_score",
            "kill_switch_fatigue_min",
            "reduce_only_fatigue_min",
        }
        missing_thresholds = sorted(required_thresholds - set(thresholds.keys()))
        if missing_thresholds:
            raise ValueError(f"execution_suggestion policy missing thresholds keys: {','.join(missing_thresholds)}")

        required_trade_types = {"breakout", "low_buy", "intraday_only", "watch", "avoid"}
        missing_bands = sorted(required_trade_types - set(position_bands.keys()))
        if missing_bands:
            raise ValueError(f"execution_suggestion policy missing position bands: {','.join(missing_bands)}")

        # Strict numeric + range checks (single source of truth, fail-fast)
        breakout_min = self._as_float(thresholds.get("breakout_min_score"), "thresholds.breakout_min_score")
        low_buy_min = self._as_float(thresholds.get("low_buy_min_score"), "thresholds.low_buy_min_score")
        watch_min = self._as_float(thresholds.get("watch_min_score"), "thresholds.watch_min_score")
        kill_switch_min = self._as_float(
            thresholds.get("kill_switch_fatigue_min"), "thresholds.kill_switch_fatigue_min"
        )
        reduce_only_min = self._as_float(
            thresholds.get("reduce_only_fatigue_min"), "thresholds.reduce_only_fatigue_min"
        )
        for name, v in {
            "breakout_min_score": breakout_min,
            "low_buy_min_score": low_buy_min,
            "watch_min_score": watch_min,
            "kill_switch_fatigue_min": kill_switch_min,
            "reduce_only_fatigue_min": reduce_only_min,
        }.items():
            if not (0.0 <= v <= 100.0):
                raise ValueError(f"execution_suggestion policy {name} out of range [0,100]")
        if not (breakout_min >= low_buy_min >= watch_min):
            raise ValueError("execution_suggestion policy thresholds must satisfy breakout >= low_buy >= watch")
        if kill_switch_min < reduce_only_min:
            raise ValueError("execution_suggestion policy requires kill_switch_fatigue_min >= reduce_only_fatigue_min")

        validated_bands: Dict[str, Dict[str, Any]] = {}
        for trade_type in required_trade_types:
            cfg = position_bands.get(trade_type)
            if not isinstance(cfg, dict):
                raise ValueError(f"execution_suggestion policy band for {trade_type} must be an object")
            mode = str(cfg.get("mode", "")).strip()
            if mode not in {"zero", "range", "fixed"}:
                raise ValueError(f"execution_suggestion policy band mode invalid for {trade_type}")
            min_v = self._as_float(cfg.get("min"), f"position_bands.{trade_type}.min")
            max_v = self._as_float(cfg.get("max"), f"position_bands.{trade_type}.max")
            if not (0.0 <= min_v <= 1.0 and 0.0 <= max_v <= 1.0):
                raise ValueError(f"execution_suggestion policy band range invalid for {trade_type}")
            if min_v > max_v:
                raise ValueError(f"execution_suggestion policy band min>max for {trade_type}")
            validated_bands[trade_type] = {"mode": mode, "min": min_v, "max": max_v}

        self.thresholds = {
            "breakout_min_score": breakout_min,
            "low_buy_min_score": low_buy_min,
            "watch_min_score": watch_min,
            "kill_switch_fatigue_min": kill_switch_min,
            "reduce_only_fatigue_min": reduce_only_min,
        }
        self.position_bands = validated_bands

    @staticmethod
    def _required_float(raw: Dict[str, Any], key: str) -> tuple[float | None, str | None]:
        value = raw.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return None, f"missing_critical_input_{key}"
        try:
            return float(value), None
        except (TypeError, ValueError):
            return None, f"invalid_critical_input_{key}"

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        score, score_err = self._required_float(raw, "score")
        if score_err:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_SCORE", "message": score_err}],
            )
        fatigue_score, fatigue_err = self._required_float(raw, "fatigue_score")
        if fatigue_err:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_FATIGUE_SCORE", "message": fatigue_err}],
            )
        has_opportunity = bool(raw.get("has_opportunity", False))
        market_validated = bool(raw.get("market_validated", False))
        lifecycle_state = str(raw.get("lifecycle_state") or "")
        stale_event = raw.get("stale_event") if isinstance(raw.get("stale_event"), dict) else {}
        is_stale = bool(stale_event.get("is_stale", False))

        breakout_min = self.thresholds["breakout_min_score"]
        low_buy_min = self.thresholds["low_buy_min_score"]
        watch_min = self.thresholds["watch_min_score"]
        kill_switch_min = self.thresholds["kill_switch_fatigue_min"]
        reduce_only_min = self.thresholds["reduce_only_fatigue_min"]

        if (is_stale and not market_validated) or score < watch_min or not has_opportunity:
            trade_type = "avoid"
        elif score >= breakout_min and market_validated:
            trade_type = "breakout"
        elif score >= low_buy_min and lifecycle_state == "Verified" and not market_validated:
            trade_type = "intraday_only"
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

        band = self.position_bands[trade_type]
        if risk_switch == "reduce_only":
            pct_min = max(0.0, float(band["min"]) * 0.5)
            pct_max = max(pct_min, float(band["max"]) * 0.5)
        elif risk_switch in {"no_trade", "kill_switch"}:
            pct_min = 0.0
            pct_max = 0.0
        else:
            pct_min = max(0.0, float(band["min"]))
            pct_max = max(pct_min, float(band["max"]))

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
                "mode": str(band["mode"]),
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
