#!/usr/bin/env python3
"""
LifecycleManager for EDT analysis layer.

C1 升级目标：
- 内部采用统一状态流（Detected→Verified→Hypothesis→Validated→Approved→Executed→Monitored→Closed→Reviewed）
- 对外继续输出兼容字段 lifecycle_state（旧口径）
- 支持回放/重试场景的有界推进（避免死循环）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class LifecycleManager(EDTModule):
    """Lifecycle state manager for event objects with internal-v2 + legacy compatibility."""

    INTERNAL_STATES = [
        "Detected",
        "Verified",
        "Hypothesis",
        "Validated",
        "Approved",
        "Executed",
        "Monitored",
        "Closed",
        "Reviewed",
    ]

    LEGACY_STATES = {
        "Detected",
        "Verified",
        "Active",
        "Continuation",
        "Exhaustion",
        "Dead",
        "Archived",
    }

    VALID_CATALYST_STATES = {
        "first_impulse",
        "continuation",
        "exhaustion",
        "dead",
    }

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("LifecycleManager", "1.1.0", config_path)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["event_id", "category", "severity", "source_rank", "detected_at"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    def _internal_to_legacy(self, internal_state: str, contradicted: bool, market_validated: bool, elapsed_hours: float) -> str:
        """内部状态映射到历史 lifecycle_state，保证下游兼容。"""
        if contradicted:
            return "Dead"

        mapping = {
            "Detected": "Detected",
            "Verified": "Verified",
            "Hypothesis": "Verified",
            "Validated": "Active",
            "Approved": "Active",
            "Executed": "Continuation",
            "Monitored": "Continuation",
            "Closed": "Archived",
            "Reviewed": "Archived",
        }

        legacy = mapping.get(internal_state, "Detected")

        # 兼容旧规则：长时间未验证的活跃状态可退化为 Exhaustion
        if legacy in {"Active", "Continuation"} and elapsed_hours >= 48 and not market_validated:
            return "Exhaustion"
        return legacy

    def _build_internal_state(self, raw: Dict[str, Any]) -> tuple[str, str]:
        """判定内部统一状态，并返回原因。"""
        source_rank = raw.get("source_rank")
        previous_lifecycle = raw.get("previous_lifecycle_state")
        elapsed_hours = float(raw.get("elapsed_hours", 0))
        contradicted = bool(raw.get("contradicted_by_new_fact", False))
        official = bool(raw.get("is_official_confirmed", False))
        market_validated = bool(raw.get("market_validated", False))
        material_update = bool(raw.get("has_material_update", False))

        # C1 新增编排输入（均为可选）
        previous_internal = raw.get("previous_internal_state")
        ai_hypothesis_ready = bool(raw.get("ai_hypothesis_ready", False))
        validation_passed = bool(raw.get("validation_passed", market_validated))
        risk_approved = bool(raw.get("risk_approved", False))
        execution_confirmed = bool(raw.get("execution_confirmed", False))
        monitoring_stable = bool(raw.get("monitoring_stable", False))
        close_conditions_met = bool(raw.get("close_conditions_met", False))
        review_completed = bool(raw.get("review_completed", False))

        retry_count = int(raw.get("retry_count", 0))
        max_retries = int(raw.get("max_retries", 3))

        if contradicted:
            return "Closed", "事件被新事实证伪或覆盖，进入关闭态"
        if review_completed:
            return "Reviewed", "复盘已完成，进入终态"

        # 兼容旧生命周期推进规则（保障现有链路无破坏）
        if previous_lifecycle in {"Active", "Continuation"} and elapsed_hours >= 48 and not material_update and not market_validated:
            return "Monitored", "超过时间窗口且边际反应减弱，进入监控衰减"
        if previous_lifecycle in {"Active", "Continuation"} and official and market_validated and elapsed_hours >= 24 and material_update:
            return "Executed", "确认后持续发酵，延续阶段保持可交易"
        if close_conditions_met:
            return "Closed", "触发关闭条件（止盈/止损/失效）"
        if execution_confirmed and monitoring_stable:
            return "Monitored", "已执行并进入稳定监控"
        if execution_confirmed:
            return "Executed", "执行确认完成"
        if risk_approved:
            return "Approved", "通过风控审批"
        if validation_passed:
            return "Validated", "通过验证条件"
        if ai_hypothesis_ready or material_update:
            return "Hypothesis", "已形成可验证假设"
        if official:
            return "Verified", "事件已确认，等待验证"
        if source_rank == "C" and not official:
            return "Detected", "来源等级不足，等待升源确认"

        # 重试有界：达到重试上限仍无进展，安全落到 Closed（可审计，不死循环）
        if previous_internal in self.INTERNAL_STATES and retry_count >= max_retries:
            return "Closed", "重试达到上限且无状态推进，安全关闭"

        return "Detected", "事件刚进入系统，等待进一步确认"

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data

        elapsed_hours = float(raw.get("elapsed_hours", 0))
        contradicted = bool(raw.get("contradicted_by_new_fact", False))
        market_validated = bool(raw.get("market_validated", False))

        internal_state, reason = self._build_internal_state(raw)
        legacy_state = self._internal_to_legacy(internal_state, contradicted, market_validated, elapsed_hours)

        if legacy_state == "Dead":
            catalyst_state = "dead"
            trade_eligibility = "blocked"
            holding_horizon = "none"
        elif legacy_state == "Exhaustion":
            catalyst_state = "exhaustion"
            trade_eligibility = "watch"
            holding_horizon = "none"
        elif legacy_state == "Continuation":
            catalyst_state = "continuation"
            trade_eligibility = "tradable"
            holding_horizon = "multiweek"
        elif legacy_state == "Active":
            catalyst_state = "first_impulse"
            trade_eligibility = "tradable"
            holding_horizon = "overnight"
        elif legacy_state == "Verified":
            catalyst_state = "first_impulse"
            trade_eligibility = "watch"
            holding_horizon = "intraday"
        elif legacy_state == "Archived":
            catalyst_state = "dead"
            trade_eligibility = "archive_only"
            holding_horizon = "none"
        else:
            catalyst_state = "first_impulse"
            trade_eligibility = "watch"
            holding_horizon = "intraday"

        next_review_at = (
            datetime.now(timezone.utc) + timedelta(hours=1 if legacy_state in {"Detected", "Verified"} else 4)
        ).isoformat()

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "event_id": raw["event_id"],
                "internal_state": internal_state,
                "lifecycle_state": legacy_state,
                "legacy_lifecycle_state": legacy_state,
                "catalyst_state": catalyst_state,
                "trade_eligibility": trade_eligibility,
                "holding_horizon": holding_horizon,
                "transition_reason": reason,
                "next_review_at": next_review_at,
                "needs_manual_review": False,
                "state_version": "lifecycle_v1.1",
                "reasoning": reason,
                "state_mapping": {
                    "internal_schema": "lifecycle_internal_v2",
                    "legacy_schema": "lifecycle_v1",
                    "compatible": True,
                },
                "audit": {
                    "module": self.name,
                    "rule_version": "lifecycle_v1.1",
                    "decision_trace": [internal_state, legacy_state, catalyst_state, trade_eligibility],
                },
            },
        )


if __name__ == "__main__":
    payload = {
        "event_id": "ME-C-20260330-001.V1.0",
        "category": "C",
        "severity": "E3",
        "source_rank": "A",
        "headline": "美国宣布新一轮关税措施",
        "detected_at": "2026-03-30T13:30:00Z",
        "is_official_confirmed": True,
        "market_validated": True,
        "has_material_update": True,
        "elapsed_hours": 4,
        "ai_hypothesis_ready": True,
        "validation_passed": True,
    }
    print(LifecycleManager().run(payload).data)
