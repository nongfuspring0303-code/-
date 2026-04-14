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
import sys
import yaml

# Ensure top-level packages (e.g. transmission_engine) are importable when
# this module is loaded from script entrypoints under scripts/ in CI.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus
from ai_semantic_analyzer import SemanticAnalyzer
from ai_conduction_selector import AIConductionSelector
from config_center import ConfigCenter
from transmission_engine.core.shock_classifier import ShockClassifier
from transmission_engine.core.factor_vectorizer import FactorVectorizer


class ConductionMapper(EDTModule):
    """Structured event conduction mapper."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("ConductionMapper", "1.0.0", config_path)
        base = Path(__file__).resolve().parent.parent
        self.chain_config_path = base / "configs" / "conduction_chain.yaml"
        self.event_to_shock_path = base / "configs" / "event_to_shock.yaml"
        self.factor_templates_path = base / "configs" / "factor_templates.yaml"
        self.event_type_lv2_mapping_path = base / "configs" / "event_type_lv2_mapping.yaml"
        self.gate_policy_path = base / "configs" / "gate_policy.yaml"
        self.metric_dictionary_path = base / "configs" / "metric_dictionary.yaml"
        self.backtest_protocol_path = base / "configs" / "backtest_protocol.yaml"

        self.config_center = ConfigCenter(config_path=config_path)
        self.config_center.register("conduction_chain", self.chain_config_path)
        self.config_center.register("event_to_shock", self.event_to_shock_path)
        self.config_center.register("factor_templates", self.factor_templates_path)
        self.config_center.register("event_type_lv2_mapping", self.event_type_lv2_mapping_path)
        self.config_center.register("gate_policy", self.gate_policy_path)
        self.config_center.register("metric_dictionary", self.metric_dictionary_path)
        self.config_center.register("backtest_protocol", self.backtest_protocol_path)

        self.semantic = SemanticAnalyzer(config_path=config_path)
        self.selector = AIConductionSelector()
        self.shock_classifier = ShockClassifier(config_dir=base / "configs")
        self.factor_vectorizer = FactorVectorizer(config_dir=base / "configs")

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

    def _load_chain_config(self) -> Dict[str, Any]:
        payload = self.config_center.get_registered("conduction_chain", {})
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _normalize_text(*parts: Any) -> str:
        return " ".join(str(part or "").lower() for part in parts).strip()

    @staticmethod
    def _keyword_match_strength(text: str, keyword: str) -> int:
        lower = text.lower()
        needle = str(keyword).strip().lower()
        if not needle:
            return 0
        if " " in needle or any(ord(ch) > 127 for ch in needle):
            return 2 if needle in lower else 0

        tokens = set()
        current = []
        for ch in lower:
            if ch.isalnum():
                current.append(ch)
            else:
                if current:
                    tokens.add("".join(current))
                    current = []
        if current:
            tokens.add("".join(current))
        return 1 if needle in tokens else 0

    @classmethod
    def _matches_any(cls, text: str, keywords: List[str]) -> bool:
        return any(cls._keyword_match_strength(text, kw) > 0 for kw in keywords)

    def _match_chain_template(
        self,
        category: str,
        headline: str,
        summary: str,
        semantic_output: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        chain_cfg = self._load_chain_config()
        templates = {item.get("id"): item for item in chain_cfg.get("chain_templates", []) if isinstance(item, dict)}
        mapping_rules = chain_cfg.get("event_to_chain_mapping", []) or []
        text = self._normalize_text(headline, summary)

        selected_chain_id = None
        selected_strength = 0
        for rule in mapping_rules:
            keywords = rule.get("event_keywords", [])
            if not isinstance(keywords, list):
                continue
            strength = max((self._keyword_match_strength(text, kw) for kw in keywords), default=0)
            if strength > selected_strength:
                selected_strength = strength
                selected_chain_id = rule.get("chain_id")

        semantic_out = semantic_output if isinstance(semantic_output, dict) else self.semantic.analyze(headline, summary)
        chosen = self.selector.choose_chain(semantic_out, selected_chain_id)
        semantic_selected = str(chosen.get("chain_id") or "")
        if semantic_selected in templates:
            selected_chain_id = semantic_selected

        category_defaults = {
            "A": "liquidity_stress_chain",
            "B": "public_health_chain",
            "C": "tariff_chain",
            "D": "geo_risk_chain",
            "E": "rate_cut_chain",
            "F": "macro_data_chain",
            "G": "market_structure_chain",
        }
        if not selected_chain_id:
            default_chain = category_defaults.get(str(category).upper())
            if default_chain in templates:
                selected_chain_id = default_chain

        if not selected_chain_id:
            return None

        template = templates.get(selected_chain_id)
        if not template:
            return None
        return template

    @staticmethod
    def _level_items(levels: List[Dict[str, Any]], target_level: str) -> List[Dict[str, Any]]:
        for level in levels:
            if level.get("level") == target_level:
                if target_level == "macro":
                    return list(level.get("factors", []))
                if target_level == "sector":
                    return list(level.get("sectors", []))
                if target_level == "theme":
                    return list(level.get("themes", []))
        return []

    @staticmethod
    def _normalize_recommended_stocks(semantic_output: Optional[Dict[str, Any]]) -> List[str]:
        if not semantic_output or not isinstance(semantic_output, dict):
            return []
        recommended = semantic_output.get("recommended_stocks", [])
        if not isinstance(recommended, list):
            return []
        normalized: List[str] = []
        seen = set()
        for symbol in recommended:
            normalized_symbol = str(symbol or "").strip().upper()
            if not normalized_symbol or normalized_symbol in seen:
                continue
            seen.add(normalized_symbol)
            normalized.append(normalized_symbol)
        return normalized

    def _build_template_mapping(self, template: Dict[str, Any], sector_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        levels = template.get("levels", []) or []
        conduction_path = [str(level.get("name", "")) for level in levels if level.get("name")]

        macro_factors = []
        for item in self._level_items(levels, "macro"):
            macro_factors.append(
                {
                    "factor": item.get("factor"),
                    "direction": item.get("direction"),
                    "strength": item.get("strength"),
                    "reason": f"模板 {template.get('id', 'unknown')} 命中",
                }
            )

        sector_impacts = []
        for item in self._level_items(levels, "sector"):
            sector_impacts.append(
                {
                    "sector": item.get("name"),
                    "direction": item.get("direction"),
                    "driver_type": "template",
                    "reason": f"模板 {template.get('id', 'unknown')} 命中",
                    "impact_score": item.get("impact_score", 0.0),
                }
            )

        stock_candidates = []
        for item in self._level_items(levels, "sector"):
            sector_name = str(item.get("name", ""))
            for candidate in sector_data:
                candidate_sector = str(candidate.get("sector") or candidate.get("industry") or "")
                if not candidate_sector:
                    continue
                if sector_name and sector_name.lower() in candidate_sector.lower():
                    stock_candidates.append(
                        {
                            "symbol": candidate.get("symbol", ""),
                            "sector": candidate_sector,
                            "direction": item.get("direction", "benefit"),
                            "event_beta": 1.0,
                            "liquidity_tier": "high",
                            "reason": f"模板 {template.get('id', 'unknown')} 关联",
                            "source": "config",
                        }
                    )

        defaults = self.config_center.get_registered("gate_policy", {}).get("conduction_mapper", {})
        confidence = float(defaults.get("template_base_confidence", 80))
        if template.get("id") == "rate_cut_chain":
            confidence = float(defaults.get("template_rate_cut_confidence", 88))
        elif template.get("id") == "inflation_shock_chain":
            confidence = float(defaults.get("template_inflation_confidence", 82))

        return {
            "macro_factors": macro_factors,
            "asset_impacts": [],
            "sector_impacts": sector_impacts,
            "stock_candidates": stock_candidates,
            "conduction_path": conduction_path or [template.get("name", "模板链路")],
            "confidence": confidence,
            "mapping_source": f"template:{template.get('id', 'unknown')}",
        }

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
                {
                    "asset_class": "fx",
                    "target": "DXY",
                    "direction": "long",
                    "confidence": float(
                        self.config_center.get_registered("gate_policy", {})
                        .get("conduction_mapper", {})
                        .get("tariff_asset_confidence", 72)
                    ),
                },
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
            "confidence": float(
                self.config_center.get_registered("gate_policy", {})
                .get("conduction_mapper", {})
                .get("tariff_confidence", 78)
            ),
        }

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _policy_mapping(
        self,
        policy_intervention: str,
        sector_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
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

        policy_cfg = self.config_center.get_registered("gate_policy", {}).get("conduction_mapper", {})
        confidence = float(policy_cfg.get("policy_base_confidence", 74))
        if sector_impacts:
            abs_moves = [abs(self._safe_float(x.get("change_pct"), 0.0)) for x in sector_impacts]
            if abs_moves:
                lower = float(policy_cfg.get("policy_confidence_min", 55))
                upper = float(policy_cfg.get("policy_confidence_max", 95))
                scale = float(policy_cfg.get("policy_confidence_scale", 8))
                base = float(policy_cfg.get("policy_confidence_base", 55))
                confidence = min(upper, max(lower, base + sum(abs_moves) / len(abs_moves) * scale))

        return {
            "macro_factors": macro_factors,
            "asset_impacts": [
                {
                    "asset_class": "equity_index",
                    "target": "SPY",
                    "direction": "long",
                    "confidence": float(policy_cfg.get("policy_asset_confidence", 68)),
                }
            ],
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

        classification = self.shock_classifier.classify(
            category=category,
            headline=headline,
            summary=summary,
            severity=raw.get("severity"),
        )
        raw_macro_factor_vector = self.factor_vectorizer.vectorize(
            event_type_lv2=classification.get("event_type_lv2", "macro_generic"),
            severity=raw.get("severity"),
            lifecycle_state=raw.get("lifecycle_state"),
            novelty_score=raw.get("novelty_score"),
            fatigue_final=raw.get("fatigue_final"),
        )

        if not headline and not summary:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "INSUFFICIENT_EVENT_CONTEXT", "message": "Headline or summary is required"}],
            )

        semantic_out = self.semantic.analyze(headline, summary)
        ai_recommended_stocks = self._normalize_recommended_stocks(semantic_out)

        template = self._match_chain_template(category, headline, summary, semantic_out)
        if template and template.get("id") == "tariff_chain":
            mapping = self._tariff_mapping()
            mapping["mapping_source"] = "template:tariff_chain"
            mapping["conduction_path"] = ["关税升级", "通胀压力上升", "增长预期下降", "出口链承压", "进口替代链受益"]
        elif template and template.get("id") == "rate_cut_chain":
            mapping = self._policy_mapping(policy_intervention, sector_data)
            mapping["mapping_source"] = "template:rate_cut_chain"
            mapping["conduction_path"] = ["政策干预预期", "流动性改善预期", "受益资产反弹"]
        elif template:
            mapping = self._build_template_mapping(template, sector_data)
        elif category == "C":
            mapping = self._tariff_mapping()
        elif category == "E":
            mapping = self._policy_mapping(policy_intervention, sector_data)
        else:
            fallback_cfg = self.config_center.get_registered("gate_policy", {}).get("conduction_mapper", {})
            mapping = {
                "macro_factors": [],
                "asset_impacts": [],
                "sector_impacts": [],
                "stock_candidates": [],
                "conduction_path": ["事件信息不足，需人工补充传导路径"],
                "confidence": float(fallback_cfg.get("fallback_confidence", 35)),
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
                "schema_version": raw.get("schema_version", "v1.1"),
                "macro_factors": mapping["macro_factors"],
                "asset_impacts": mapping["asset_impacts"],
                "sector_impacts": mapping["sector_impacts"],
                "stock_candidates": mapping["stock_candidates"],
                "shock_profile": classification.get("shock_profile"),
                "raw_macro_factor_vector": raw_macro_factor_vector,
                "event_type_lv1": classification.get("event_type_lv1"),
                "event_type_lv2": classification.get("event_type_lv2"),
                "classification_confidence": classification.get("classification_confidence"),
                "market_impact_confidence": classification.get("market_impact_confidence"),
                "ai_recommendation_source": "semantic_analyzer" if ai_recommended_stocks else "none",
                "ai_recommended_stocks": ai_recommended_stocks,
                "ai_recommendation_chain": semantic_out.get("recommended_chain", ""),
                "ai_recommendation_confidence": semantic_out.get("confidence", 0),
                "time_horizons": {
                    "intraday": "headline冲击主导",
                    "overnight": "等待二次验证",
                    "multiweek": "确认后转向基本面传导",
                },
                "conduction_path": mapping["conduction_path"],
                "confidence": mapping["confidence"],
                "needs_manual_review": needs_manual_review,
                "mapping_source": mapping.get("mapping_source", "rule"),
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
