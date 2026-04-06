#!/usr/bin/env python3
"""
ConductionMapper for EDT analysis layer.

This module maps event categories into macro factors, asset classes, sectors,
and stock candidates while enforcing the project's no-direct-stock-mapping
rule.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
import yaml

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class ConductionMapper(EDTModule):
    """Structured event conduction mapper."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("ConductionMapper", "1.0.0", config_path)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["event_id", "category", "severity", "lifecycle_state"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    def _load_sector_mapping(self) -> Dict[str, List[str]]:
        path = Path(__file__).resolve().parent.parent / "configs" / "sector_impact_mapping.yaml"
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return payload.get("mapping", {})
        except Exception:
            return {}

    def _apply_sector_mapping(self, sector_impacts: List[Dict[str, Any]], sector_data: List[Dict[str, Any]]) -> None:
        if not sector_data:
            return
        mapping = self._load_sector_mapping()
        if not mapping:
            return
        available = {item.get("sector"): item for item in sector_data if item.get("sector")}
        for impact in sector_impacts:
            tag = impact.get("sector")
            candidates = mapping.get(tag, [])
            for name in candidates:
                if name in available:
                    impact["sector"] = name
                    break

    def _tariff_mapping(self) -> Dict[str, Any]:
        return {
            "macro_factors": [
                {"factor": "inflation", "direction": "up", "strength": "high", "reason": "进口成本上升"},
                {"factor": "growth", "direction": "down", "strength": "medium", "reason": "贸易摩擦压制出口和投资"},
            ],
            "asset_impacts": [
                {"asset_class": "fx", "target": "DXY", "direction": "long", "confidence": 72},
            ],
            "sector_impacts": [
                {
                    "sector": "industrials_export",
                    "direction": "hurt",
                    "driver_type": "beta_alpha",
                    "reason": "出口链承压",
                }
            ],
            "stock_candidates": [
                {
                    "symbol": "CAT",
                    "sector": "industrials_export",
                    "direction": "short",
                    "event_beta": 1.2,
                    "liquidity_tier": "high",
                    "reason": "出口敏感且宏观传导一致",
                }
            ],
            "conduction_path": ["关税升级", "通胀压力上升", "增长预期下降", "出口链承压", "进口替代链受益"],
            "confidence": 78,
        }

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _policy_mapping(self, policy_intervention: str, sector_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        macro_factors: List[Dict[str, Any]] = [
            {"factor": "liquidity", "direction": "up", "strength": "high", "reason": "强政策干预预期改善流动性"},
            {"factor": "rates", "direction": "down", "strength": "medium", "reason": "刺激预期对应宽松利率环境"},
        ]
        conduction_path = ["危机升级", "政策干预预期", "流动性改善预期", "受益资产反弹"]
        if policy_intervention != "STRONG":
            macro_factors[0]["strength"] = "medium"

        # Real-data path: derive sector impact from live ETF sector snapshot.
        sector_impacts: List[Dict[str, Any]] = []
        for item in sector_data:
            change_pct = self._safe_float(item.get("change_pct"), 0.0)
            # Skip near-flat moves to reduce noise.
            if abs(change_pct) < 0.1:
                continue
            direction = "benefit" if change_pct >= 0 else "hurt"
            sector_name = item.get("industry") or item.get("sector") or "未知板块"
            sector_impacts.append(
                {
                    "sector": sector_name,
                    "direction": direction,
                    "driver_type": "market_validation",
                    "reason": f"实时ETF变化 {change_pct:+.2f}%",
                    "change_pct": round(change_pct, 2),
                }
            )

        # Fallback to baseline policy mapping if live sector moves unavailable.
        if not sector_impacts:
            sector_impacts = [
                {
                    "sector": "金融",
                    "direction": "benefit",
                    "driver_type": "beta",
                    "reason": "流动性宽松预期支撑估值",
                }
            ]

        stock_candidates: List[Dict[str, Any]] = []
        for impact in sector_impacts[:2]:
            direction = "long" if impact.get("direction") == "benefit" else "short"
            stock_candidates.append(
                {
                    "symbol": "JPM" if "金融" in str(impact.get("sector", "")) else "SPY",
                    "sector": impact.get("sector", "未知板块"),
                    "direction": direction,
                    "event_beta": 0.9,
                    "liquidity_tier": "high",
                    "reason": impact.get("reason", "实时板块映射"),
                }
            )

        confidence = 74
        if sector_impacts:
            abs_moves = [abs(self._safe_float(x.get("change_pct"), 0.0)) for x in sector_impacts]
            if abs_moves:
                confidence = int(min(95, max(55, 55 + sum(abs_moves) / len(abs_moves) * 8)))

        return {
            "macro_factors": macro_factors,
            "asset_impacts": [{"asset_class": "equity_index", "target": "SPY", "direction": "long", "confidence": 68}],
            "sector_impacts": sector_impacts,
            "stock_candidates": stock_candidates,
            "conduction_path": conduction_path,
            "confidence": confidence,
        }

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data

        category = raw["category"]
        headline = raw.get("headline", "")
        summary = raw.get("summary", "")
        policy_intervention = raw.get("policy_intervention", "NONE")
        sector_data = raw.get("sector_data", []) or []

        if not headline and not summary:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "INSUFFICIENT_EVENT_CONTEXT", "message": "Headline or summary is required"}],
            )

        if category == "C":
            mapping = self._tariff_mapping()
        elif category == "E":
            mapping = self._policy_mapping(policy_intervention, sector_data)
        else:
            mapping = {
                "macro_factors": [],
                "asset_impacts": [],
                "sector_impacts": [],
                "stock_candidates": [],
                "conduction_path": ["事件信息不足，需人工补充传导路径"],
                "confidence": 35,
            }

        self._apply_sector_mapping(mapping["sector_impacts"], sector_data)

        if not mapping["macro_factors"] or not mapping["sector_impacts"]:
            mapping["stock_candidates"] = []
            needs_manual_review = True
        else:
            needs_manual_review = False

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "event_id": raw["event_id"],
                "macro_factors": mapping["macro_factors"],
                "asset_impacts": mapping["asset_impacts"],
                "sector_impacts": mapping["sector_impacts"],
                "stock_candidates": mapping["stock_candidates"],
                "time_horizons": {
                    "intraday": "headline冲击主导",
                    "overnight": "等待二次验证",
                    "multiweek": "确认后转向基本面传导",
                },
                "conduction_path": mapping["conduction_path"],
                "confidence": mapping["confidence"],
                "needs_manual_review": needs_manual_review,
                "audit": {
                    "module": self.name,
                    "rule_version": "conduction_v1",
                    "decision_trace": mapping["conduction_path"],
                },
            },
        )


if __name__ == "__main__":
    payload = {
        "event_id": "ME-C-20260330-001.V1.0",
        "category": "C",
        "severity": "E3",
        "headline": "美国宣布新一轮关税措施",
        "summary": "进口成本上升，出口链承压",
        "lifecycle_state": "Active",
        "narrative_tags": ["trade_war", "inflation_shock"],
        "policy_intervention": "NONE",
    }
    print(ConductionMapper().run(payload).data)
