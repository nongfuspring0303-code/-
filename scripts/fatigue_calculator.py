#!/usr/bin/env python3
"""
FatigueCalculator for EDT analysis layer.

This module calculates category fatigue, narrative-tag fatigue, and the final
fatigue constraint used by scoring and execution decisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class FatigueCalculator(EDTModule):
    """Narrative fatigue calculator."""

    def __init__(self, config_path: Optional[str] = None, state_store: Optional[Any] = None):
        self.state_store = state_store
        super().__init__("FatigueCalculator", "1.0.0", config_path)
        self._init_fatigue_config()

    def _init_fatigue_config(self) -> None:
        """Initialize fatigue-specific configuration from loaded config."""
        if not self.config:
            # 默认配置（向后兼容）
            self.count_thresholds = {2: 0, 3: 20, 4: 40, 5: 60, 6: 80, 7: 100}
            self.fatigue_discount_threshold = 70
            self.fatigue_discount_factor = 0.5
            self.watch_mode_threshold = 85
            self.dead_event_reset_days = 30
            self.take_profit_penalty_factor = 0.5
        else:
            self.count_thresholds = self.config.get("count_to_fatigue_score", {})
            self.fatigue_discount_threshold = self.config.get("fatigue_discount_threshold", 70)
            self.fatigue_discount_factor = self.config.get("fatigue_discount_factor", 0.5)
            self.watch_mode_threshold = self.config.get("watch_mode_threshold", 85)
            self.dead_event_reset_days = self.config.get("dead_event_reset_days", 30)
            self.take_profit_penalty_factor = self.config.get("take_profit_penalty_factor", 0.5)
        self._load_bucket_thresholds()

    def _load_bucket_thresholds(self) -> None:
        default = {"critical_min": 85, "high_min": 70, "medium_min": 40, "low_min": 1}
        thresholds = {}
        if isinstance(self.config, dict):
            thresholds = dict((self.config.get("fatigue") or {}).get("bucket_thresholds", {}) or {})
        if not thresholds:
            policy_path = Path(__file__).resolve().parent.parent / "configs" / "lifecycle_fatigue_contract_policy.yaml"
            if policy_path.exists():
                policy = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
                thresholds = dict(((policy.get("fatigue") or {}).get("bucket_thresholds", {}) or {}))
        merged = {**default, **thresholds}
        self.bucket_thresholds = {
            "critical_min": int(merged.get("critical_min", 85)),
            "high_min": int(merged.get("high_min", 70)),
            "medium_min": int(merged.get("medium_min", 40)),
            "low_min": int(merged.get("low_min", 1)),
        }

    def _fatigue_bucket(self, score: int) -> str:
        if score >= self.bucket_thresholds["critical_min"]:
            return "critical"
        if score >= self.bucket_thresholds["high_min"]:
            return "high"
        if score >= self.bucket_thresholds["medium_min"]:
            return "medium"
        if score >= self.bucket_thresholds["low_min"]:
            return "low"
        return "none"

    def _get_active_counts_from_db(self, category: Optional[str] = None,
                                   narrative_tags: Optional[list] = None) -> tuple[int, Dict[str, int]]:
        """
        从 SQLite 状态表查询活跃事件数。

        Args:
            category: 事件类别（可选）
            narrative_tags: 叙事标签列表（可选）

        Returns:
            (category_active_count, tag_active_counts)
        """
        if self.state_store is None:
            return 0, {}

        try:
            import sqlite3
            db_path = self.state_store._db_path if hasattr(self.state_store, '_db_path') else None
            if not db_path:
                return 0, {}

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询非 Dead 状态的事件；分类信息保存在 metadata 中而不是独立列
            cursor.execute(
                "SELECT metadata FROM event_states WHERE lifecycle_state != 'Dead'"
            )
            rows = cursor.fetchall()
            conn.close()

            # 统计类别活跃数
            category_count = 0
            if category:
                import json

                category_count = 0
                for row in rows:
                    try:
                        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if metadata.get("category") == category:
                        category_count += 1

            # 统计标签活跃数
            tag_counts: Dict[str, int] = {}
            if narrative_tags:
                import json
                for row in rows:
                    try:
                        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                        row_tags = metadata.get("narrative_tags", [])
                        for tag in narrative_tags:
                            if tag in row_tags:
                                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                    except (json.JSONDecodeError, TypeError):
                        continue

            return category_count, tag_counts
        except Exception as e:
            # 查询失败时返回空值，不影响主流程
            print(f"Warning: Failed to query active counts from DB: {e}")
            return 0, {}

    def _score_from_count(self, count: int) -> int:
        """根据配置的阈值计算疲劳度分数。"""
        # 找到最接近的阈值
        thresholds = sorted(self.count_thresholds.keys())
        for threshold in reversed(thresholds):
            if count >= threshold:
                return self.count_thresholds[threshold]
        # 如果小于所有阈值，返回 0
        return 0

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["event_id", "category", "lifecycle_state"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data

        # 尝试从数据库查询活跃事件数（如果提供了 state_store）
        if self.state_store and "category_active_count" not in raw:
            narrative_tags = raw.get("narrative_tags", [])
            category_count, tag_counts = self._get_active_counts_from_db(
                category=raw.get("category"),
                narrative_tags=narrative_tags if narrative_tags else None
            )
            # 使用查询结果作为默认值
            raw.setdefault("category_active_count", category_count)
            if tag_counts:
                raw.setdefault("tag_active_counts", tag_counts)

        if "category_active_count" not in raw:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "MISSING_HISTORY_CONTEXT", "message": "Missing category_active_count"}],
            )

        category_count = int(raw.get("category_active_count", 0))
        tag_counts = raw.get("tag_active_counts", {}) or {}
        days_since_last_dead = float(raw.get("days_since_last_dead", 0))

        fatigue_category = self._score_from_count(category_count)
        fatigue_tag = max((self._score_from_count(int(count)) for count in tag_counts.values()), default=0)

        if raw.get("lifecycle_state") == "Dead" and days_since_last_dead >= self.dead_event_reset_days:
            fatigue_category = 0
            fatigue_tag = 0
            reset_eligible = True
        else:
            reset_eligible = False

        fatigue_final = max(fatigue_category, fatigue_tag)
        fatigue_bucket = self._fatigue_bucket(fatigue_final)
        watch_mode = fatigue_final > self.watch_mode_threshold

        if fatigue_final > self.fatigue_discount_threshold:
            discount = self.fatigue_discount_factor
            take_profit_penalty = self.take_profit_penalty_factor
        else:
            discount = 1.0
            take_profit_penalty = 0.0

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "event_id": raw["event_id"],
                "fatigue_category": fatigue_category,
                "fatigue_tag": fatigue_tag,
                "fatigue_final": fatigue_final,
                "fatigue_score": fatigue_final,
                "fatigue_bucket": fatigue_bucket,
                "watch_mode": watch_mode,
                "a_minus_1_discount_factor": discount,
                "take_profit_penalty": take_profit_penalty,
                "reset_eligible": reset_eligible,
                "reasoning": "最终疲劳度取类别疲劳与标签疲劳的最大值",
                "audit": {
                    "module": self.name,
                    "rule_version": "fatigue_v2",
                    "decision_trace": [fatigue_category, fatigue_tag, fatigue_final, fatigue_bucket, watch_mode],
                },
            },
        )


if __name__ == "__main__":
    payload = {
        "event_id": "ME-E-20260331-002.V1.0",
        "category": "E",
        "lifecycle_state": "Continuation",
        "narrative_tags": ["policy_pivot"],
        "category_active_count": 6,
        "tag_active_counts": {"policy_pivot": 7},
        "days_since_last_dead": 3,
    }
    print(FatigueCalculator().run(payload).data)
