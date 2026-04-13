#!/usr/bin/env python3
"""
Execution modules for EDT (T4.1 - T4.4).
"""

from __future__ import annotations

from pathlib import Path
import math
from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class LiquidityChecker(EDTModule):
    """Check liquidity state (GREEN / YELLOW / RED)."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("LiquidityChecker", "1.0.0", config_path or _default_config_path())

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["vix", "ted", "correlation", "spread_pct"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        correlation = _safe_float(input_data["correlation"], 0.0)
        spread_pct = _safe_float(input_data["spread_pct"], 0.0)
        if not (-1 <= correlation <= 1):
            return False, "correlation must be in [-1,1]"
        if spread_pct < 0:
            return False, "spread_pct must be >=0"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        vix = _safe_float(raw.get("vix"), 0.0)
        ted = _safe_float(raw.get("ted"), 0.0)
        corr = _safe_float(raw.get("correlation"), 0.0)
        spread_pct = _safe_float(raw.get("spread_pct"), 0.0)

        thresholds = self._get_config("modules.LiquidityChecker.params.thresholds", {})
        micro = self._get_config("modules.LiquidityChecker.params.micro_thresholds", {})

        green = thresholds.get("green", {})
        yellow = thresholds.get("yellow", {})
        red = thresholds.get("red", {})

        state = "GREEN"
        reason = "Within normal liquidity range."

        if (
            vix >= red.get("vix_min", 30)
            or ted >= red.get("ted_min", 100)
            or corr >= red.get("correlation_min", 0.8)
            or spread_pct >= micro.get("spread_danger", 0.01)
        ):
            state = "RED"
            reason = "System stress or dangerous micro liquidity."
        elif (
            (yellow.get("vix_min", 20) <= vix <= yellow.get("vix_max", 30))
            or (yellow.get("ted_min", 50) <= ted <= yellow.get("ted_max", 100))
            or (yellow.get("correlation_min", 0.6) <= corr <= yellow.get("correlation_max", 0.8))
            or spread_pct >= micro.get("spread_warning", 0.005)
        ):
            # 检查严重程度：多个指标同时警告 或 接近危险阈值
            warning_count = sum([
                yellow.get("vix_min", 20) <= vix <= yellow.get("vix_max", 30),
                yellow.get("ted_min", 50) <= ted <= yellow.get("ted_max", 100),
                yellow.get("correlation_min", 0.6) <= corr <= yellow.get("correlation_max", 0.8),
                spread_pct >= micro.get("spread_warning", 0.005)
            ])
            
            # 检查是否接近危险阈值
            near_danger = (
                vix >= 28 or  # 接近 RED 的 30
                ted >= 90 or  # 接近 RED 的 100
                corr >= 0.75 or  # 接近 RED 的 0.8
                spread_pct >= 0.008  # 接近 RED 的 0.01
            )
            
            if warning_count >= 2 or near_danger:
                state = "YELLOW_STRONG"
                reason = "Severe liquidity warning, multiple indicators in warning range or near danger."
            else:
                state = "YELLOW"
                reason = "Liquidity warning, position should be reduced."
        elif (
            vix <= green.get("vix_max", 20)
            and ted <= green.get("ted_max", 50)
            and corr <= green.get("correlation_max", 0.6)
        ):
            state = "GREEN"
            reason = "Normal liquidity."

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "liquidity_state": state,
                "spread_multiplier": max(1.0, spread_pct / max(0.0001, micro.get("spread_warning", 0.005))),
                "reason": reason,
                "metrics": {"vix": vix, "ted": ted, "correlation": corr, "spread_pct": spread_pct},
            },
        )


class RiskGatekeeper(EDTModule):
    """Apply G1-G6 risk gates and output final action."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("RiskGatekeeper", "1.0.0", config_path or _default_config_path())

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["event_state", "fatigue_index", "liquidity_state", "correlation", "score", "severity", "A1"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        try:
            correlation = float(input_data["correlation"])
            fatigue_index = float(input_data["fatigue_index"])
            score = float(input_data["score"])
            a1 = float(input_data["A1"])
        except (TypeError, ValueError):
            return False, "numeric fields must be valid numbers"
        if not all(math.isfinite(value) for value in (correlation, fatigue_index, score, a1)):
            return False, "numeric fields must be finite"
        if not (-1 <= correlation <= 1):
            return False, "correlation must be in [-1,1]"
        if not (0 <= fatigue_index <= 100):
            return False, "fatigue_index must be in [0,100]"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        decisions = []

        params_cfg = self._get_config("modules.RiskGatekeeper.params", {})
        gates_cfg = params_cfg.get("gates", {})

        def finalize(
            *,
            final_action: str,
            position_multiplier: float,
            direction: str,
            first_triggered_gate: str | None,
            human_confirm_required: bool,
            warnings: list[str] | None = None,
            rejection_reason: str = "",
            matched_score_tier: str | None = None,
        ) -> ModuleOutput:
            warnings_final = warnings or []
            triggered = [item["gate"] for item in decisions if item.get("triggered")]
            summary = {
                "triggered_gates": triggered,
                "threshold_snapshot": {
                    "g1_spread_multiplier_threshold": float(params_cfg.get("g1_liquidity", {}).get("spread_multiplier_threshold", 5)),
                    "g3_fatigue_threshold": float(params_cfg.get("g3_fatigue", {}).get("threshold", 85)),
                    "g4_correlation_threshold": float(params_cfg.get("g4_correlation", {}).get("threshold", 0.8)),
                    "g6_a1_threshold": float(params_cfg.get("g6_policy", {}).get("a1_threshold", 60)),
                },
                "final_action": final_action,
                "rejection_reason": rejection_reason,
                "model_version": str(raw.get("model_id", "unknown")),
                "prompt_version": str(raw.get("prompt_version", "unknown")),
                "mapping_version": str(raw.get("mapping_version", "factor_map_v1")),
                "temperature": raw.get("temperature"),
                "timeout_ms": raw.get("timeout_ms"),
                "matched_score_tier": matched_score_tier,
            }
            reasoning = (
                f"final_action={final_action}; triggered={triggered}; "
                f"rejection_reason={rejection_reason or 'none'}; mapping={summary['mapping_version']}"
            )
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data={
                    "gate_decisions": decisions,
                    "final_action": final_action,
                    "position_multiplier": position_multiplier,
                    "direction": direction,
                    "first_triggered_gate": first_triggered_gate,
                    "human_confirm_required": human_confirm_required,
                    "warnings": warnings_final,
                    "reasoning": reasoning,
                    "decision_summary": summary,
                },
            )

        # G1: Liquidity blackhole (config-driven)
        spread = float(raw.get("spread_multiplier", 1.0))
        liquidity_state = raw["liquidity_state"]
        g1_cfg = params_cfg.get("g1_liquidity", {})
        g1_spread_th = float(g1_cfg.get("spread_multiplier_threshold", 5))
        g1_red_state = str(g1_cfg.get("red_state_value", "RED"))
        g1_final_action = str(g1_cfg.get("final_action_on_trigger", "BLOCK"))
        g1_human_confirm = bool(g1_cfg.get("human_confirm_required", True))
        g1_action = gates_cfg.get("G1_liquidity", {}).get("action", "BLOCK_NEW")

        if spread > g1_spread_th or liquidity_state == g1_red_state:
            decisions.append({"gate": "G1", "triggered": True, "action": g1_action, "reason": "Liquidity blackhole"})
            return finalize(
                final_action=g1_final_action,
                position_multiplier=0.0,
                direction="no_change",
                first_triggered_gate="G1",
                human_confirm_required=g1_human_confirm,
                rejection_reason="liquidity_blackhole",
            )
        decisions.append({"gate": "G1", "triggered": False, "action": "PASS"})

        # G2: lifecycle dead (config-driven)
        g2_cfg = params_cfg.get("g2_lifecycle", {})
        g2_blocked_states = set(g2_cfg.get("blocked_states", ["Dead", "Archived"]))
        g2_final_action = str(g2_cfg.get("final_action_on_trigger", "FORCE_CLOSE"))
        g2_human_confirm = bool(g2_cfg.get("human_confirm_required", False))
        g2_action = gates_cfg.get("G2_lifecycle", {}).get("action", "FORCE_CLOSE")

        if raw["event_state"] in g2_blocked_states:
            decisions.append({"gate": "G2", "triggered": True, "action": g2_action, "reason": "Event dead"})
            return finalize(
                final_action=g2_final_action,
                position_multiplier=0.0,
                direction="no_change",
                first_triggered_gate="G2",
                human_confirm_required=g2_human_confirm,
                rejection_reason="lifecycle_blocked_state",
            )
        decisions.append({"gate": "G2", "triggered": False, "action": "PASS"})

        # G3: fatigue (config-driven)
        fatigue = float(raw["fatigue_index"])
        g3_cfg = params_cfg.get("g3_fatigue", {})
        g3_threshold = float(g3_cfg.get("threshold", 85))
        g3_final_action = str(g3_cfg.get("final_action_on_trigger", "WATCH"))
        g3_human_confirm = bool(g3_cfg.get("human_confirm_required", False))
        g3_action = gates_cfg.get("G3_fatigue", {}).get("action", "BLOCK_NEW")

        if fatigue > g3_threshold:
            decisions.append({"gate": "G3", "triggered": True, "action": g3_action, "reason": f"Fatigue > {g3_threshold}"})
            return finalize(
                final_action=g3_final_action,
                position_multiplier=0.0,
                direction="no_change",
                first_triggered_gate="G3",
                human_confirm_required=g3_human_confirm,
                rejection_reason="fatigue_exceeded",
            )
        decisions.append({"gate": "G3", "triggered": False, "action": "PASS"})

        # G7: AI safety fallback and review gate (optional)
        g7_cfg = params_cfg.get("g7_ai_review", {})
        g7_enabled = bool(g7_cfg.get("enabled", False))
        safe_cfg = params_cfg.get("ai_safe_defaults", {})
        ai_failure_mode = str(raw.get("ai_failure_mode", "none")).strip().lower()
        if bool(safe_cfg.get("enabled", False)) and ai_failure_mode in {"timeout", "error"}:
            selected = dict(safe_cfg.get("on_ai_timeout" if ai_failure_mode == "timeout" else "on_ai_error", {}))
            action = str(selected.get("action", "WATCH"))
            reason = str(selected.get("reason", f"ai_{ai_failure_mode}_safe_default"))
            decisions.append({"gate": "G7", "triggered": True, "action": "AI_SAFE_DEFAULT", "reason": reason})
            return finalize(
                final_action=action,
                position_multiplier=0.0,
                direction="no_change",
                first_triggered_gate="G7",
                human_confirm_required=False,
                rejection_reason=reason,
            )

        ai_review_required = bool(raw.get("ai_review_required", g7_cfg.get("required", False)))
        ai_review_passed = bool(raw.get("ai_review_passed", not ai_review_required))
        if g7_enabled and ai_review_required and not ai_review_passed:
            reject_action = str(g7_cfg.get("action_on_reject", "WATCH"))
            decisions.append(
                {
                    "gate": "G7",
                    "triggered": True,
                    "action": "AI_REVIEW_REJECT",
                    "reason": "AI review required but not passed",
                }
            )
            return finalize(
                final_action=reject_action,
                position_multiplier=0.0,
                direction="no_change",
                first_triggered_gate="G7",
                human_confirm_required=bool(g7_cfg.get("human_confirm_required", False)),
                rejection_reason="ai_review_rejected",
            )
        decisions.append({"gate": "G7", "triggered": False, "action": "PASS"})

        # G4: correlation collapse (config-driven)
        corr = float(raw["correlation"])
        severity = raw["severity"]
        position_multiplier = 1.0
        warnings = []
        g4_cfg = params_cfg.get("g4_correlation", {})
        g4_threshold = float(g4_cfg.get("threshold", 0.8))
        g4_e4_multiplier = float(g4_cfg.get("e4_position_multiplier", 0.5))
        g4_default_multiplier = float(g4_cfg.get("default_position_multiplier", 0.0))
        g4_warning = str(g4_cfg.get("warning", "Correlation collapse mode."))
        g4_action = gates_cfg.get("G4_correlation", {}).get("action", "A15_ADJUST")

        if corr > g4_threshold:
            decisions.append(
                {
                    "gate": "G4",
                    "triggered": True,
                    "action": g4_action,
                    "reason": f"Correlation > {g4_threshold}",
                }
            )
            position_multiplier = g4_e4_multiplier if severity == "E4" else g4_default_multiplier
            warnings.append(g4_warning)
        else:
            decisions.append({"gate": "G4", "triggered": False, "action": "PASS"})

        # G5: score tier (config-driven from PositionSizer tiers)
        score = float(raw["score"])
        tier_multiplier = 0.0
        matched_score_tier = None
        tiers_cfg = self._get_config("modules.PositionSizer.params.tiers", {})
        for tier_name, tier in tiers_cfg.items():
            rng = tier.get("score_range", [])
            if not isinstance(rng, list) or len(rng) != 2:
                continue
            lo, hi = float(rng[0]), float(rng[1])
            if lo <= score <= hi:
                tier_multiplier = float(tier.get("position_pct", 0.0))
                matched_score_tier = tier_name
                decisions.append(
                    {
                        "gate": "G5",
                        "triggered": True,
                        "action": "POSITION_TIER",
                        "reason": f"score={score:.2f} matched={tier_name}",
                    }
                )
                break
        if matched_score_tier is None:
            decisions.append({"gate": "G5", "triggered": False, "action": "POSITION_TIER", "reason": f"score={score:.2f} no_matching_tier"})

        # G6: policy intervention direction flip (config-driven)
        direction = "no_change"
        g6_cfg = params_cfg.get("g6_policy", {})
        g6_intervention_value = str(g6_cfg.get("intervention_value", "STRONG"))
        g6_a1_threshold = float(g6_cfg.get("a1_threshold", 60))
        g6_direction_on_trigger = str(g6_cfg.get("direction_on_trigger", "flip"))
        g6_action = gates_cfg.get("G6_policy", {}).get("action", "DIRECTION_FLIP")

        if raw.get("policy_intervention") == g6_intervention_value and float(raw["A1"]) >= g6_a1_threshold:
            decisions.append(
                {
                    "gate": "G6",
                    "triggered": True,
                    "action": g6_action,
                    "reason": f"{g6_intervention_value} policy + A1>={g6_a1_threshold}",
                }
            )
            direction = g6_direction_on_trigger
        else:
            decisions.append({"gate": "G6", "triggered": False, "action": "PASS"})

        final_multiplier = round(position_multiplier * tier_multiplier, 4)
        final_action = "EXECUTE" if final_multiplier > 0 else "WATCH"
        return finalize(
            final_action=final_action,
            position_multiplier=final_multiplier,
            direction=direction,
            first_triggered_gate=None,
            human_confirm_required=False,
            warnings=warnings,
            rejection_reason="" if final_action == "EXECUTE" else "score_or_multiplier_below_threshold",
        )


class PositionSizer(EDTModule):
    """Calculate position size based on score tier and liquidity."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("PositionSizer", "1.0.0", config_path or _default_config_path())

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["score", "liquidity_state", "risk_gate_multiplier", "account_equity"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        try:
            score = float(input_data["score"])
            risk_gate_multiplier = float(input_data["risk_gate_multiplier"])
            account_equity = float(input_data["account_equity"])
        except (TypeError, ValueError):
            return False, "numeric fields must be valid numbers"
        if not all(math.isfinite(value) for value in (score, risk_gate_multiplier, account_equity)):
            return False, "numeric fields must be finite"
        if account_equity < 0:
            return False, "account_equity must be >=0"
        if risk_gate_multiplier < 0:
            return False, "risk_gate_multiplier must be >=0"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        score = float(raw["score"])
        liquidity_state = raw["liquidity_state"]
        risk_gate_multiplier = float(raw["risk_gate_multiplier"])
        account_equity = float(raw["account_equity"])

        tiers = self._get_config("modules.PositionSizer.params.tiers", {})
        if score >= 80:
            tier_name = "G1"
        elif score >= 60:
            tier_name = "G2"
        elif score >= 40:
            tier_name = "G3"
        elif score >= 20:
            tier_name = "G4"
        else:
            tier_name = "G5"

        tier_position = float(tiers.get(tier_name, {}).get("position_pct", 0.0))
        liq_adj = self._get_config("modules.PositionSizer.params.liquidity_adjustments", {}).get(liquidity_state, 0.0)
        final_pct = max(0.0, min(1.0, tier_position * float(liq_adj) * risk_gate_multiplier))
        final_notional = round(account_equity * final_pct, 2)

        # Production guardrails: daily loss and event cap.
        daily_cfg = self._get_config("modules.PositionSizer.params.daily", {})
        max_loss_pct = float(daily_cfg.get("max_loss_pct", 0.05))
        max_open_events = int(daily_cfg.get("max_open_events", 5))
        daily_loss_pct = float(raw.get("daily_loss_pct", 0.0))
        current_open_events = int(raw.get("current_open_events", 0))
        breach_reasons = []
        if daily_loss_pct >= max_loss_pct:
            breach_reasons.append(f"daily_loss_pct {daily_loss_pct:.4f} >= max_loss_pct {max_loss_pct:.4f}")
            final_pct = 0.0
            final_notional = 0.0
        if current_open_events >= max_open_events:
            breach_reasons.append(f"open_events {current_open_events} >= max_open_events {max_open_events}")
            final_pct = 0.0
            final_notional = 0.0

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "score_tier": tier_name,
                "base_position_pct": tier_position,
                "final_position_pct": final_pct,
                "final_notional": final_notional,
                "liquidity_adjustment": liq_adj,
                "risk_limit_breached": bool(breach_reasons),
                "risk_limit_reason": breach_reasons[0] if breach_reasons else None,
                "risk_limit_reasons": breach_reasons,
            },
        )


class ExitManager(EDTModule):
    """Generate stop loss / take profit / time stop plan."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("ExitManager", "1.0.0", config_path or _default_config_path())

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["entry_price", "risk_per_share", "direction"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        try:
            entry_price = float(input_data["entry_price"])
            risk_per_share = float(input_data["risk_per_share"])
        except (TypeError, ValueError):
            return False, "entry_price and risk_per_share must be valid numbers"
        if not all(math.isfinite(value) for value in (entry_price, risk_per_share)):
            return False, "entry_price and risk_per_share must be finite"
        if entry_price <= 0 or risk_per_share <= 0:
            return False, "entry_price and risk_per_share must be >0"
        if str(input_data["direction"]).strip().lower() not in ("long", "short"):
            return False, "direction must be long or short"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        entry = float(raw["entry_price"])
        r = float(raw["risk_per_share"])
        direction = str(raw["direction"]).strip().lower()
        hold_days = int(raw.get("hold_days", 0))
        profit_r = float(raw.get("profit_r", 0.0))
        profit_retrace = float(raw.get("profit_retrace", 0.0))

        if direction == "long":
            hard_stop = round(entry - 2 * r, 4)
            tp = [round(entry + 1 * r, 4), round(entry + 2 * r, 4), round(entry + 3 * r, 4)]
        else:
            hard_stop = round(entry + 2 * r, 4)
            tp = [round(entry - 1 * r, 4), round(entry - 2 * r, 4), round(entry - 3 * r, 4)]

        triggers = []
        if profit_retrace >= 0.5 and profit_r > 0:
            triggers.append({"type": "trailing", "action": "CLOSE_50%"})
        if hold_days >= 5 and profit_r < 1:
            triggers.append({"type": "time", "action": "EVALUATE_OR_REDUCE"})

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "hard_stop": hard_stop,
                "take_profit_levels": tp,
                "dynamic_triggers": triggers,
                "direction": direction,
            },
        )
