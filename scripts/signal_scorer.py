#!/usr/bin/env python3
"""
SignalScorer for EDT analysis layer.

This module consolidates the analysis-layer scores into a final strategy score,
position tier, and direction while applying fatigue, correlation, and policy
intervention rules required by the project documents.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class SignalScorer(EDTModule):
    """Final analysis-layer score consolidator."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("SignalScorer", "1.0.0", config_path)
        self.weights = {
            "A0": 0.25,
            "A-1": 0.20,
            "A1": 0.25,
            "A1.5": 0.20,
            "A0.5": 0.10,
        }

    def _weights_from_config(self) -> Dict[str, float]:
        cfg = self._get_config("modules.SignalScorer.params.weights", {})
        weights = dict(self.weights)
        for key in weights:
            try:
                if key in cfg:
                    weights[key] = float(cfg[key])
            except (TypeError, ValueError):
                continue
        return weights

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["event_id", "severity", "fatigue_final", "correlation"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        adjustments = []
        weights = self._weights_from_config()

        missing_scores = [key for key in ("A0", "A-1", "A1", "A1.5", "A0.5") if key not in raw]
        if missing_scores:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "MISSING_SCORES", "message": f"Missing score fields: {', '.join(missing_scores)}"}],
            )

        if raw.get("watch_mode", False):
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data={
                    "event_id": raw["event_id"],
                    "score_raw": 0,
                    "score": 0,
                    "score_tier": "G5",
                    "position_pct": 0.0,
                    "direction": "neutral",
                    "adjustments_applied": ["watch_mode_block"],
                    "weight_details": {
                        "w_A0": weights["A0"],
                        "w_A-1": weights["A-1"],
                        "w_A1": weights["A1"],
                        "w_A1.5": weights["A1.5"],
                        "w_A0.5": weights["A0.5"],
                        "effective_A-1": 0,
                        "effective_A1.5": 0,
                    },
                    "watch_mode": True,
                    "reasoning": "高疲劳进入Watch模式，直接阻断评分执行",
                },
            )

        severity = raw["severity"]
        a0 = float(raw["A0"])
        a_minus_1 = float(raw["A-1"]) * float(raw.get("a_minus_1_discount_factor", 1.0))
        a1 = float(raw["A1"])
        a1_5 = float(raw["A1.5"])
        a0_5 = float(raw["A0.5"])
        correlation = float(raw["correlation"])
        direction = raw.get("base_direction", "neutral")

        if severity == "E4":
            weights["A-1"] = max(0.10, weights["A-1"] - 0.10)
            weights["A1"] += 0.10
            weights["A0.5"] += 0.10
            adjustments.append("E4_weight_adjustment")

        if raw.get("fatigue_final", 0) > 70 or float(raw.get("a_minus_1_discount_factor", 1.0)) < 1.0:
            adjustments.append("fatigue_discount")

        if correlation > 0.8:
            if severity == "E4":
                a1_5 = a1_5 * 0.35
            else:
                a1_5 = 0.0
            adjustments.append("correlation_breakdown_A1.5_discount")

        score_raw = (
            weights["A0"] * a0
            + weights["A-1"] * a_minus_1
            + weights["A1"] * a1
            + weights["A1.5"] * a1_5
            - weights["A0.5"] * a0_5
        )

        score = max(-100.0, min(100.0, score_raw))

        if raw.get("is_crowded", False):
            # 拥挤度折价: High级 → Score -30%
            score = score * 0.70
            adjustments.append("crowded_trade_discount")

        if raw.get("narrative_mode") == "Narrative-Driven":
            # Narrative模式: 降仓50%
            # 在 tier 计算后应用
            adjustments.append("narrative_mode_position_cut")

        # 强政策干预：增强当前方向而不是翻转
        # 降息/量化宽松等本身就是政策干预，不应该翻转
        # 这里的 policy_intervention 应该指"额外"的政策干预，如救市计划
        # 但由于难以区分，我们改为增强方向：提高置信度等级
        # 先计算初始等级和仓位
        if score >= 80:
            tier = "G1"
            position_pct = 0.8
        elif score >= 60:
            tier = "G2"
            position_pct = 0.5
        elif score >= 40:
            tier = "G3"
            position_pct = 0.2
        elif score >= 20:
            tier = "G4"
            position_pct = 0.0
        else:
            tier = "G5"
            position_pct = 0.0

        # 强政策干预：增强当前方向而不是翻转
        # 降息/量化宽松等本身就是政策干预，不应该翻转
        # 这里的 policy_intervention 应该指"额外"的政策干预，如救市计划
        # 但由于难以区分，我们改为增强方向：提高置信度等级
        if raw.get("policy_intervention") == "STRONG":
            # 强政策干预增强信号：提升置信度等级
            # G4 -> G3, G3 -> G2, 保持更高等级不变
            if tier == "G4":
                tier = "G3"
                position_pct = 0.2
            elif tier == "G3":
                tier = "G2"
                position_pct = 0.5
            adjustments.append("policy_intervention_strength_boost")

        # Narrative模式: 降仓50%
        if raw.get("narrative_mode") == "Narrative-Driven":
            position_pct = position_pct * 0.50

        if tier == "G5":
            direction = "neutral"

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "event_id": raw["event_id"],
                "score_raw": score_raw,
                "score": score,
                "score_tier": tier,
                "position_pct": position_pct,
                "direction": direction,
                "adjustments_applied": adjustments,
                "weight_details": {
                    "w_A0": weights["A0"],
                    "w_A-1": weights["A-1"],
                    "w_A1": weights["A1"],
                    "w_A1.5": weights["A1.5"],
                    "w_A0.5": weights["A0.5"],
                    "effective_A-1": a_minus_1,
                    "effective_A1.5": a1_5,
                },
                "watch_mode": False,
                "reasoning": "按分析层评分口径综合计算最终分数",
                "audit": {
                    "module": self.name,
                    "rule_version": raw.get("weights_version", "score_v1"),
                    "decision_trace": adjustments or ["base_score_only"],
                },
            },
        )


if __name__ == "__main__":
    payload = {
        "event_id": "ME-C-20260330-001.V1.0",
        "severity": "E3",
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "fatigue_final": 20,
        "a_minus_1_discount_factor": 1.0,
        "correlation": 0.4,
        "is_crowded": False,
        "narrative_mode": "Fact-Driven",
        "policy_intervention": "NONE",
        "base_direction": "long",
        "watch_mode": False,
        "weights_version": "score_v1",
    }
    print(SignalScorer().run(payload).data)
