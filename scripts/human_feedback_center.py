#!/usr/bin/env python3
"""
C-6 人工反馈接口与配置中心后端支持。
提供以下能力：
1) 可读写板块映射配置与优质股票池配置
2) 记录人工纠错反馈
3) 生成回传给 A/B 模块的反馈包
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import json

import yaml


@dataclass
class FeedbackRecord:
    trace_id: str
    source_module: str
    target_module: str
    feedback_type: str
    original_value: Any
    corrected_value: Any
    reason: str
    created_at: str


class HumanFeedbackCenter:
    def __init__(self, base_dir: str | None = None):
        root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
        self.root = root
        self.config_dir = root / "configs"
        self.log_dir = root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.sector_mapping_file = self.config_dir / "sector_impact_mapping.yaml"
        self.stock_pool_file = self.config_dir / "premium_stock_pool.yaml"
        self.feedback_file = self.log_dir / "human_feedback.jsonl"

    def get_sector_mapping(self) -> dict[str, Any]:
        return self._read_yaml(self.sector_mapping_file)

    def update_sector_mapping(self, payload: dict[str, Any]) -> None:
        payload["updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        self._write_yaml(self.sector_mapping_file, payload)

    def get_stock_pool(self) -> dict[str, Any]:
        return self._read_yaml(self.stock_pool_file)

    def update_stock_pool(self, payload: dict[str, Any]) -> None:
        payload["updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        self._write_yaml(self.stock_pool_file, payload)

    def submit_feedback(
        self,
        *,
        trace_id: str,
        source_module: str,
        target_module: str,
        feedback_type: str,
        original_value: Any,
        corrected_value: Any,
        reason: str,
    ) -> dict[str, Any]:
        record = FeedbackRecord(
            trace_id=trace_id,
            source_module=source_module,
            target_module=target_module,
            feedback_type=feedback_type,
            original_value=original_value,
            corrected_value=corrected_value,
            reason=reason,
            created_at=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        )
        self._append_feedback(record)
        return {
            "status": "ok",
            "message": "feedback accepted",
            "record": asdict(record),
        }

    def list_feedback(self, target_module: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.feedback_file.exists():
            return rows
        with open(self.feedback_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if target_module and obj.get("target_module") != target_module:
                    continue
                rows.append(obj)
        return rows[-limit:]

    def export_feedback_package(self, target_module: str) -> dict[str, Any]:
        rows = self.list_feedback(target_module=target_module)
        return {
            "target_module": target_module,
            "schema_version": "v1.0",
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "count": len(rows),
            "items": rows,
        }

    def _append_feedback(self, record: FeedbackRecord) -> None:
        with open(self.feedback_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    center = HumanFeedbackCenter()
    print("sector_mapping_items:", len(center.get_sector_mapping().get("mappings", [])))
    print("stock_pool_items:", len(center.get_stock_pool().get("stocks", [])))
