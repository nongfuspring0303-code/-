#!/usr/bin/env python3
"""
ConductionMapper for EDT analysis layer.

This module maps event categories into macro factors, asset classes, sectors,
and stock candidates while enforcing the project's no-direct-stock-mapping
rule.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import sys
import yaml
import logging

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

logger = logging.getLogger(__name__)


class ConductionMapper(EDTModule):
    """Structured event conduction mapper."""

    _SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
    _INVALID_SYMBOLS = {"N/A", "NA", "NONE", "NULL", "UNKNOWN", "UNDEFINED", "TBD"}
    _TIER1_EVENT_TYPES: set[str] = set()
    _NO_RECOMMEND_TIER3_EVENT_TYPES: set[str] = {"other", "natural_disaster", "shipping", "healthcare"}
    _NO_RECOMMEND_EVENT_TYPES: set[str] = {"other", "natural_disaster"}
    _WATCHLIST_DEFAULT_EVENT_TYPES: set[str] = set()
    _RECOMMENDED_MIN_CONFIDENCE = 1.01
    _WATCHLIST_MIN_CONFIDENCE = 0.50
    _ENERGY_TICKERS: set[str] = set()
    _NON_US_BLOCK_PROXY_TICKERS: set[str] = set()
    _US_TECH_FIN_PROXY_TICKERS: set[str] = set()
    _HEALTHCARE_HINTS = (
        "healthcare",
        "hospital",
        "drug",
        "pharma",
        "biotech",
        "vaccine",
        "medical",
        "医药",
        "医疗",
        "疫苗",
        "制药",
    )
    _ASIA_TECH_HINTS = ("东京电子", "台积电", "tsmc", "asml", "三星", "semiconductor", "chip")
    _NON_US_MARKET_HINTS: tuple[str, ...] = tuple()
    _GEO_ENERGY_ALLOWED_HINTS: tuple[str, ...] = tuple()

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
        self.tier1_mapping_rules_path = base / "configs" / "tier1_mapping_rules.yaml"
        self.causal_contract_policy_path = base / "configs" / "causal_contract_policy.yaml"

        self.config_center = ConfigCenter(config_path=config_path)
        self.config_center.register("conduction_chain", self.chain_config_path)
        self.config_center.register("event_to_shock", self.event_to_shock_path)
        self.config_center.register("factor_templates", self.factor_templates_path)
        self.config_center.register("event_type_lv2_mapping", self.event_type_lv2_mapping_path)
        self.config_center.register("gate_policy", self.gate_policy_path)
        self.config_center.register("metric_dictionary", self.metric_dictionary_path)
        self.config_center.register("backtest_protocol", self.backtest_protocol_path)
        self.config_center.register("tier1_mapping_rules", self.tier1_mapping_rules_path)
        self.config_center.register("causal_contract_policy", self.causal_contract_policy_path)

        self.semantic = SemanticAnalyzer(config_path=config_path)
        self.selector = AIConductionSelector()
        self.shock_classifier = ShockClassifier(config_dir=base / "configs")
        self.factor_vectorizer = FactorVectorizer(config_dir=base / "configs")
        self._sector_mapping = self._load_sector_mapping()
        self._sector_whitelist = self._load_sector_whitelist()
        self._tier1_guardrails = self._load_tier1_rules_guardrails()
        self._apply_guardrails_config()

    def _set_safe_guardrails_fallback(self, reason: str) -> None:
        self._TIER1_EVENT_TYPES = set()
        self._NO_RECOMMEND_TIER3_EVENT_TYPES = {"other", "natural_disaster", "shipping", "healthcare"}
        self._NO_RECOMMEND_EVENT_TYPES = {"other", "natural_disaster"}
        self._WATCHLIST_DEFAULT_EVENT_TYPES = set()
        self._RECOMMENDED_MIN_CONFIDENCE = 1.01
        self._WATCHLIST_MIN_CONFIDENCE = 0.50
        self._ENERGY_TICKERS = set()
        self._NON_US_BLOCK_PROXY_TICKERS = set()
        self._US_TECH_FIN_PROXY_TICKERS = set()
        self._NON_US_MARKET_HINTS = tuple()
        self._GEO_ENERGY_ALLOWED_HINTS = tuple()
        logger.warning("tier1 guardrails missing/invalid; entering safe fallback mode: %s", reason)

    @staticmethod
    def _clean_text_value(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if text.lower() in {"none", "null", "unknown", "undefined", "n/a"}:
            return ""
        return text

    @staticmethod
    def _normalize_confidence_value(value: Any, default: float = 0.0) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = float(default)
        if score < 0:
            return 0.0
        if score <= 1.0:
            return score
        return min(1.0, score / 100.0)

    def _apply_guardrails_config(self) -> None:
        """Override class-level defaults with values from tier1_mapping_rules.yaml recommendation_guardrails."""
        gr = self._tier1_guardrails
        if not gr:
            self._set_safe_guardrails_fallback("recommendation_guardrails absent")
            return

        # Tier1 event types
        raw_t1 = gr.get("tier1_event_types")
        if isinstance(raw_t1, list) and raw_t1:
            self._TIER1_EVENT_TYPES = {str(x).strip() for x in raw_t1 if str(x).strip()}

        # Tier3 no-recommend types
        raw_t3 = gr.get("no_recommend_tier3_event_types")
        if isinstance(raw_t3, list):
            self._NO_RECOMMEND_TIER3_EVENT_TYPES = {str(x).strip() for x in raw_t3 if str(x).strip()}

        # Non-recommend and watchlist default event types
        raw_no_recommend = gr.get("no_recommend_event_types")
        if isinstance(raw_no_recommend, list):
            self._NO_RECOMMEND_EVENT_TYPES = {str(x).strip() for x in raw_no_recommend if str(x).strip()}
        raw_watchlist_default = gr.get("watchlist_default_event_types")
        if isinstance(raw_watchlist_default, list):
            self._WATCHLIST_DEFAULT_EVENT_TYPES = {str(x).strip() for x in raw_watchlist_default if str(x).strip()}

        # Thresholds
        thresholds = gr.get("recommendation_thresholds", {}) or {}
        if isinstance(thresholds, dict):
            self._RECOMMENDED_MIN_CONFIDENCE = float(thresholds.get("recommended_min_confidence", 0.70))
            self._WATCHLIST_MIN_CONFIDENCE = float(thresholds.get("watchlist_min_confidence", 0.50))
        else:
            self._RECOMMENDED_MIN_CONFIDENCE = 1.01
            self._WATCHLIST_MIN_CONFIDENCE = 0.50

        # Proxy blocklists
        bl = gr.get("proxy_blocklists", {}) or {}
        if isinstance(bl, dict):
            raw_et = bl.get("energy_tickers")
            if isinstance(raw_et, list):
                self._ENERGY_TICKERS = {str(x).strip().upper() for x in raw_et if str(x).strip()}
            raw_nu = bl.get("non_us_block_proxy_tickers")
            if isinstance(raw_nu, list):
                self._NON_US_BLOCK_PROXY_TICKERS = {str(x).strip().upper() for x in raw_nu if str(x).strip()}
            raw_utf = bl.get("us_tech_fin_proxy_tickers")
            if isinstance(raw_utf, list):
                self._US_TECH_FIN_PROXY_TICKERS = {str(x).strip().upper() for x in raw_utf if str(x).strip()}

        # Market hints
        mh = gr.get("market_hints", {}) or {}
        if isinstance(mh, dict):
            raw_nu_h = mh.get("non_us")
            if isinstance(raw_nu_h, list):
                self._NON_US_MARKET_HINTS = tuple(str(x).strip() for x in raw_nu_h if str(x).strip())
            raw_ge = mh.get("geo_energy_allowed")
            if isinstance(raw_ge, list):
                self._GEO_ENERGY_ALLOWED_HINTS = tuple(str(x).strip() for x in raw_ge if str(x).strip())

    def _load_tier1_rules_guardrails(self) -> dict:
        """Load guardrails from tier1_mapping_rules.yaml; return empty dict on failure."""
        try:
            cfg = yaml.safe_load(self.tier1_mapping_rules_path.read_text(encoding="utf-8")) or {}
            gr = cfg.get("recommendation_guardrails", {}) or {}
            if isinstance(gr, dict):
                return gr
        except Exception as exc:
            logger.warning("failed to load tier1 guardrails: %s", exc)
        return {}

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

    def _load_sector_whitelist(self) -> set[str]:
        path = Path(__file__).resolve().parent.parent / "configs" / "sector_impact_mapping.yaml"
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return set()

        whitelist: set[str] = set()
        for item in payload.get("mappings", []) or []:
            if not isinstance(item, dict):
                continue
            sector = self._clean_text_value(item.get("sector", ""))
            if sector:
                whitelist.add(sector)

        mapping = payload.get("mapping", {})
        if isinstance(mapping, dict):
            for values in mapping.values():
                if not isinstance(values, list):
                    continue
                for sector in values:
                    sector_name = self._clean_text_value(sector)
                    if sector_name:
                        whitelist.add(sector_name)

        tier1_rules = self._load_tier1_rules()
        base_weights = tier1_rules.get("base_sector_weights", {}) if isinstance(tier1_rules, dict) else {}
        if isinstance(base_weights, dict):
            for sectors in base_weights.values():
                if not isinstance(sectors, dict):
                    continue
                for sector in sectors.keys():
                    sector_name = self._clean_text_value(sector)
                    if sector_name:
                        whitelist.add(sector_name)
        ticker_pool = tier1_rules.get("ticker_pool", {}) if isinstance(tier1_rules, dict) else {}
        if isinstance(ticker_pool, dict):
            for sector in ticker_pool.keys():
                sector_name = self._clean_text_value(sector)
                if sector_name:
                    whitelist.add(sector_name)

        return whitelist

    def _normalize_sector_name(self, sector: Any) -> str:
        raw = str(sector or "").strip()
        if not raw:
            return ""
        if raw in self._sector_whitelist:
            return raw
        raw_lower = raw.lower()
        for candidate_name in self._sector_whitelist:
            if candidate_name.lower() == raw_lower:
                return candidate_name
        for mapped_key, mapped_values in self._sector_mapping.items():
            if str(mapped_key or "").strip().lower() != raw_lower:
                continue
            if isinstance(mapped_values, list):
                for candidate in mapped_values:
                    candidate_name = self._clean_text_value(candidate)
                    if candidate_name:
                        return candidate_name
        return raw

    @staticmethod
    def _resolve_sector_snapshot_name(item: Dict[str, Any]) -> str:
        # Prefer the canonical sector field from live snapshots; fall back to the localized label.
        sector = ConductionMapper._clean_text_value(item.get("sector", ""))
        if sector:
            return sector
        return ConductionMapper._clean_text_value(item.get("industry", ""))

    def _load_chain_config(self) -> Dict[str, Any]:
        payload = self.config_center.get_registered("conduction_chain", {})
        return payload if isinstance(payload, dict) else {}

    def _load_tier1_rules(self) -> Dict[str, Any]:
        payload = self.config_center.get_registered("tier1_mapping_rules", {})
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
        templates: Dict[str, Dict[str, Any]] = {}
        duplicate_ids: set[str] = set()
        for item in chain_cfg.get("chain_templates", []) or []:
            if not isinstance(item, dict):
                continue
            template_id = self._clean_text_value(item.get("id"))
            if not template_id:
                continue
            if template_id in templates:
                duplicate_ids.add(template_id)
                continue
            templates[template_id] = item
        if duplicate_ids:
            logger.warning("duplicate chain template ids detected: %s", sorted(duplicate_ids))
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
        # Keep deterministic rule hit precedence: semantic chain should not
        # override an explicit keyword-matched chain.
        if selected_strength == 0 and semantic_selected in templates:
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
        semantic_type_defaults = {
            "geo_political": "geo_risk_chain",
            "energy": "energy_supply_chain",
            "commodity": "commodity_price_chain",
            "monetary": "rate_cut_chain",
            "inflation": "inflation_shock_chain",
            "pandemic": "public_health_chain",
        }
        if not selected_chain_id:
            semantic_event_type = str(semantic_out.get("event_type", "")).strip().lower()
            semantic_chain = semantic_type_defaults.get(semantic_event_type)
            if semantic_chain in templates:
                selected_chain_id = semantic_chain

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
    def _is_valid_symbol(symbol: Any) -> bool:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return False
        if normalized in ConductionMapper._INVALID_SYMBOLS:
            return False
        if not ConductionMapper._SYMBOL_RE.match(normalized):
            return False
        return any(ch.isalpha() for ch in normalized)

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
            if not ConductionMapper._is_valid_symbol(normalized_symbol):
                continue
            if normalized_symbol in seen:
                continue
            seen.add(normalized_symbol)
            normalized.append(normalized_symbol)
        return normalized

    @staticmethod
    def _normalize_entity_stocks(semantic_output: Optional[Dict[str, Any]]) -> List[str]:
        if not semantic_output or not isinstance(semantic_output, dict):
            return []
        entities = semantic_output.get("entities", [])
        if not isinstance(entities, list):
            return []

        out: List[str] = []
        seen = set()
        for item in entities:
            if not isinstance(item, dict):
                continue
            entity_type = str(item.get("type", "")).strip().lower()
            candidate_values: List[Any] = []
            if entity_type in {"ticker", "symbol", "stock"}:
                candidate_values.append(item.get("value"))
            for key in ("symbol", "ticker", "stock", "resolved_symbol", "canonical_symbol"):
                candidate_values.append(item.get(key))

            resolved_symbol = ""
            for candidate in candidate_values:
                symbol = ConductionMapper._clean_text_value(candidate).upper()
                if ConductionMapper._is_valid_symbol(symbol):
                    resolved_symbol = symbol
                    break
            if not resolved_symbol or resolved_symbol in seen:
                continue
            seen.add(resolved_symbol)
            out.append(resolved_symbol)
        return out

    @staticmethod
    def _merge_stock_candidates(
        base_candidates: List[Dict[str, Any]],
        semantic_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()

        for candidate in base_candidates + semantic_candidates:
            symbol = str(candidate.get("symbol", "")).strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            merged.append(candidate)
        return merged

    def _build_semantic_stock_candidates(
        self,
        semantic_output: Optional[Dict[str, Any]],
        sector_impacts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not semantic_output or not isinstance(semantic_output, dict):
            return []

        recommended = self._normalize_recommended_stocks(semantic_output)
        entity_symbols = self._normalize_entity_stocks(semantic_output)

        symbols: List[str] = []
        seen = set()
        for symbol in recommended + entity_symbols:
            if symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
        if not symbols:
            return []

        sentiment = str(semantic_output.get("sentiment", "neutral")).strip().lower()
        if sentiment == "positive":
            direction = "long"
        elif sentiment == "negative":
            direction = "short"
        else:
            direction = "watch"

        sector_name = self._clean_text_value((sector_impacts or [{}])[0].get("sector", "")) or "未知板块"
        transmission = semantic_output.get("transmission_candidates", [])
        if not isinstance(transmission, list):
            transmission = []
        transmission_hint = ",".join(str(x).strip() for x in transmission if str(x).strip())[:120]

        candidates: List[Dict[str, Any]] = []
        for symbol in symbols[:5]:
            reason = "AI semantic recommendation"
            if transmission_hint:
                reason = f"AI semantic recommendation ({transmission_hint})"
            candidates.append(
                {
                    "symbol": symbol,
                    "sector": sector_name,
                    "direction": direction,
                    "reason": reason,
                    "source": "semantic",
                }
            )
        return candidates

    def _extract_subtype(self, semantic_event_type: str, headline: str, summary: str, semantic_output: Optional[Dict[str, Any]]) -> str:
        rules = self._load_tier1_rules().get("subtype_rules", {})
        candidates = rules.get(semantic_event_type, []) if isinstance(rules, dict) else []
        if not isinstance(candidates, list):
            return ""
        text = self._normalize_text(headline, summary)
        if isinstance(semantic_output, dict):
            transmissions = semantic_output.get("transmission_candidates", [])
            if isinstance(transmissions, list):
                text = f"{text} {' '.join(str(x or '') for x in transmissions)}".strip()
        for rule in candidates:
            if not isinstance(rule, dict):
                continue
            keywords = rule.get("keywords", [])
            if isinstance(keywords, list) and self._matches_any(text, [str(x) for x in keywords]):
                return str(rule.get("subtype", "")).strip()
        return ""

    def _build_sector_weight_view(
        self,
        semantic_event_type: str,
        subtype: str,
        headline: str,
        summary: str,
        semantic_output: Optional[Dict[str, Any]],
        sector_impacts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        rules = self._load_tier1_rules()
        base = rules.get("base_sector_weights", {}) if isinstance(rules, dict) else {}
        raw = base.get(semantic_event_type, {}) if isinstance(base, dict) else {}
        weights: Dict[str, float] = {}
        for k, v in (raw.items() if isinstance(raw, dict) else []):
            sector_name = self._normalize_sector_name(k)
            score = self._safe_float(v, 0.0)
            if sector_name and score > 0:
                weights[sector_name] = score

        if not weights:
            for impact in sector_impacts:
                sector_name = self._normalize_sector_name(impact.get("sector", ""))
                impact_score = self._safe_float(impact.get("impact_score"), 0.0)
                if sector_name and impact_score > 0:
                    weights[sector_name] = max(weights.get(sector_name, 0.0), impact_score)

        subtype_rules = rules.get("subtype_rules", {}) if isinstance(rules, dict) else {}
        event_rules = subtype_rules.get(semantic_event_type, []) if isinstance(subtype_rules, dict) else []
        text = self._normalize_text(headline, summary)
        if isinstance(semantic_output, dict):
            transmissions = semantic_output.get("transmission_candidates", [])
            if isinstance(transmissions, list):
                text = f"{text} {' '.join(str(x or '') for x in transmissions)}".strip()
        preferred_primary = ""
        for rule in event_rules if isinstance(event_rules, list) else []:
            if not isinstance(rule, dict):
                continue
            if subtype and str(rule.get("subtype", "")).strip() != subtype:
                continue
            keywords = rule.get("keywords", [])
            if subtype or (isinstance(keywords, list) and self._matches_any(text, [str(x) for x in keywords])):
                boosts = rule.get("boost", {})
                if isinstance(boosts, dict):
                    for k, v in boosts.items():
                        sector_name = self._normalize_sector_name(k)
                        if not sector_name:
                            continue
                        weights[sector_name] = weights.get(sector_name, 0.0) + self._safe_float(v, 0.0)
                suppress = rule.get("suppress", {})
                if isinstance(suppress, dict):
                    for k, v in suppress.items():
                        sector_name = self._normalize_sector_name(k)
                        if not sector_name:
                            continue
                        weights[sector_name] = max(0.0, weights.get(sector_name, 0.0) - self._safe_float(v, 0.0))
                required = rule.get("required_sectors", [])
                if isinstance(required, list):
                    for sector in required:
                        sector_name = self._normalize_sector_name(sector)
                        if sector_name:
                            weights[sector_name] = max(weights.get(sector_name, 0.0), 0.01)
                candidate_primary = self._normalize_sector_name(rule.get("primary_sector", ""))
                if candidate_primary:
                    preferred_primary = candidate_primary
                break

        cleaned: Dict[str, float] = {}
        for sector_name, score in weights.items():
            if sector_name and score > 0:
                cleaned[sector_name] = score
        total = sum(cleaned.values())
        if total <= 0:
            return {"sector_weights": {}, "primary_sector": "", "secondary_sectors": [], "weight_quality_score": 0.0}

        normalized = {k: round(v / total, 4) for k, v in cleaned.items()}
        ranked = sorted(normalized.items(), key=lambda kv: (-kv[1], kv[0]))
        top_ranked = ranked[:3]
        if top_ranked:
            top_total = sum(v for _, v in top_ranked)
            normalized = {k: round(v / top_total, 4) for k, v in top_ranked}
            ranked = sorted(normalized.items(), key=lambda kv: (-kv[1], kv[0]))
        primary = ranked[0][0] if ranked else ""
        if preferred_primary and preferred_primary in normalized:
            primary = preferred_primary
        secondaries = [k for k, _ in ranked if k != primary][:2]
        quality = max(0.0, 100.0 - abs(1.0 - sum(normalized.values())) * 100.0)
        return {
            "sector_weights": normalized,
            "primary_sector": primary,
            "secondary_sectors": secondaries,
            "weight_quality_score": round(quality, 2),
        }

    def _build_ticker_pool_candidates(
        self,
        semantic_output: Optional[Dict[str, Any]],
        subtype: str,
        sector_weight_view: Dict[str, Any],
        sector_impacts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rules = self._load_tier1_rules()
        ticker_pool = rules.get("ticker_pool", {}) if isinstance(rules, dict) else {}
        rec_rules = rules.get("recommendation_rules", {}) if isinstance(rules, dict) else {}
        if not isinstance(ticker_pool, dict):
            return []

        direct = set(self._normalize_recommended_stocks(semantic_output)) | set(self._normalize_entity_stocks(semantic_output))
        event_strength = self._normalize_confidence_value((semantic_output or {}).get("confidence"), 0.0)
        direct_bonus = self._safe_float(rec_rules.get("direct_mention_bonus"), 0.25)
        inferred_penalty = self._safe_float(rec_rules.get("inferred_penalty"), 0.08)
        floor = self._safe_float(rec_rules.get("min_confidence_floor"), 0.45)
        high = self._safe_float(rec_rules.get("min_confidence_high"), 0.75)
        mid = self._safe_float(rec_rules.get("min_confidence_mid"), 0.60)
        max_high = int(self._safe_float(rec_rules.get("max_recommended_high_conf"), 5))
        max_mid = int(self._safe_float(rec_rules.get("max_recommended_mid_conf"), 3))
        max_low = int(self._safe_float(rec_rules.get("max_recommended_low_conf"), 1))

        sector_to_direction: Dict[str, str] = {}
        for impact in sector_impacts:
            sector_name = self._normalize_sector_name(impact.get("sector", ""))
            if sector_name and sector_name not in sector_to_direction:
                sector_to_direction[sector_name] = str(impact.get("direction", "watch"))

        rows: List[Dict[str, Any]] = []
        for sector_name, weight in (sector_weight_view.get("sector_weights", {}) or {}).items():
            themes = ticker_pool.get(sector_name, {})
            if not isinstance(themes, dict):
                continue
            for theme, tickers in themes.items():
                if not isinstance(tickers, list):
                    continue
                for ticker in tickers:
                    symbol = str(ticker or "").strip().upper()
                    if not self._is_valid_symbol(symbol):
                        continue
                    direct_mentioned = symbol in direct
                    subtype_match = bool(theme and subtype and (subtype in str(theme).lower() or str(theme).lower() in subtype))
                    subtype_bonus = 0.08 if subtype_match else 0.0
                    score = float(weight) + subtype_bonus + (direct_bonus if direct_mentioned else -inferred_penalty) + 0.2 * event_strength
                    if score < floor:
                        continue
                    if not direct_mentioned and float(weight) < 0.18:
                        continue
                    rows.append(
                        {
                            "symbol": symbol,
                            "sector": sector_name,
                            "direction": sector_to_direction.get(sector_name, "watch"),
                            "event_beta": round(max(0.3, min(1.5, score)), 2),
                            "reason": f"sector_weight={weight:.2f}, theme={theme}, subtype_match={subtype_match}, direct={direct_mentioned}",
                            "source": "tier1_ticker_pool",
                            "source_sector": sector_name,
                            "source_theme": str(theme),
                            "confidence": round(max(0.0, min(1.0, score)), 2),
                            "whether_direct_ticker_mentioned": direct_mentioned,
                        }
                    )

        if not rows:
            return []
        rows.sort(key=lambda x: (x.get("confidence", 0.0), x.get("whether_direct_ticker_mentioned", False)), reverse=True)
        if event_strength >= high:
            limit = max_high
        elif event_strength >= mid:
            limit = max_mid
        else:
            limit = max_low
        return rows[: max(0, limit)]

    def _split_recommendation_buckets(
        self,
        semantic_event_type: str,
        headline: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        text = self._normalize_text(headline)
        out = {"candidates": list(candidates), "recommended": [], "watchlist": [], "rejected": [], "drop_diagnostics": []}
        non_us_hint = any(h in text for h in self._NON_US_MARKET_HINTS)
        geo_energy_allowed = any(h in text for h in self._GEO_ENERGY_ALLOWED_HINTS)
        def _record_drop(candidate: Dict[str, Any], drop_reason: str, status: str) -> Dict[str, Any]:
            c = dict(candidate)
            c["drop_reason"] = drop_reason
            c["rejection_reason"] = drop_reason
            c["drop_diagnostics"] = {"status": status, "semantic_event_type": semantic_event_type}
            out["drop_diagnostics"].append(
                {
                    "symbol": c.get("symbol"),
                    "sector": c.get("sector"),
                    "drop_reason": drop_reason,
                    "status": status,
                    "confidence": self._safe_float(c.get("confidence"), 0.0),
                }
            )
            return c
        for cand in candidates:
            symbol = str(cand.get("symbol", "")).strip().upper()
            confidence = self._safe_float(cand.get("confidence"), 0.0)
            reason = str(cand.get("reason", ""))
            penalties = []
            # Semantic mismatch guard: Asia-tech headlines should not prioritize US energy tickers.
            if any(h in text for h in self._ASIA_TECH_HINTS) and symbol in self._ENERGY_TICKERS:
                c = _record_drop(cand, "semantic_mismatch_asia_tech_vs_energy", "rejected")
                out["rejected"].append(c)
                continue
            if non_us_hint and symbol in self._ENERGY_TICKERS and not geo_energy_allowed:
                confidence -= 0.30
                penalties.append("non_us_energy_penalty")
            # Tier3: no recommendation by default unless directly mentioned.
            if semantic_event_type in self._NO_RECOMMEND_TIER3_EVENT_TYPES and not bool(cand.get("whether_direct_ticker_mentioned", False)):
                c = dict(cand)
                c["confidence"] = round(max(0.0, confidence), 2)
                c["drop_reason"] = "tier3_no_recommend"
                c["rejection_reason"] = "tier3_no_recommend"
                c["drop_diagnostics"] = {"status": "rejected", "semantic_event_type": semantic_event_type}
                out["drop_diagnostics"].append(
                    {
                        "symbol": c.get("symbol"),
                        "sector": c.get("sector"),
                        "drop_reason": "tier3_no_recommend",
                        "status": "rejected",
                        "confidence": c["confidence"],
                    }
                )
                out["rejected"].append(c)
                continue
            # Tier2: watchlist-first unless directly mentioned.
            if semantic_event_type in self._WATCHLIST_DEFAULT_EVENT_TYPES and not bool(cand.get("whether_direct_ticker_mentioned", False)):
                c = dict(cand)
                c["confidence"] = round(max(0.0, confidence), 2)
                c["drop_reason"] = "tier2_watchlist_default"
                c["rejection_reason"] = "tier2_watchlist_default"
                c["drop_diagnostics"] = {"status": "watchlist", "semantic_event_type": semantic_event_type}
                out["drop_diagnostics"].append(
                    {
                        "symbol": c.get("symbol"),
                        "sector": c.get("sector"),
                        "drop_reason": "tier2_watchlist_default",
                        "status": "watchlist",
                        "confidence": c["confidence"],
                    }
                )
                out["watchlist"].append(c)
                continue
            # Strong negative rule: low-signal event types default to watchlist unless direct mention.
            if semantic_event_type in self._NO_RECOMMEND_EVENT_TYPES and not bool(cand.get("whether_direct_ticker_mentioned", False)):
                if non_us_hint and symbol in self._US_TECH_FIN_PROXY_TICKERS:
                    confidence -= 0.25
                    penalties.append("non_us_tech_fin_penalty")
                c = dict(cand)
                c["confidence"] = round(max(0.0, confidence), 2)
                if penalties:
                    c["penalties"] = penalties
                c["drop_reason"] = "other_event_watch_only"
                c["rejection_reason"] = "other_event_watch_only"
                c["drop_diagnostics"] = {"status": "watchlist", "semantic_event_type": semantic_event_type}
                out["drop_diagnostics"].append(
                    {
                        "symbol": c.get("symbol"),
                        "sector": c.get("sector"),
                        "drop_reason": "other_event_watch_only",
                        "status": "watchlist",
                        "confidence": c["confidence"],
                    }
                )
                out["watchlist"].append(c)
                continue
            confidence = max(0.0, min(1.0, confidence))
            c_view = dict(cand)
            c_view["confidence"] = round(confidence, 2)
            if penalties:
                c_view["penalties"] = penalties
            if confidence >= self._RECOMMENDED_MIN_CONFIDENCE:
                out["recommended"].append(c_view)
            elif confidence >= self._WATCHLIST_MIN_CONFIDENCE:
                out["watchlist"].append(c_view)
            else:
                c_view["drop_reason"] = "low_confidence"
                c_view["rejection_reason"] = "low_confidence"
                c_view["drop_diagnostics"] = {"status": "rejected", "semantic_event_type": semantic_event_type}
                out["drop_diagnostics"].append(
                    {
                        "symbol": c_view.get("symbol"),
                        "sector": c_view.get("sector"),
                        "drop_reason": "low_confidence",
                        "status": "rejected",
                        "confidence": c_view["confidence"],
                    }
                )
                out["rejected"].append(c_view)
        return out

    @staticmethod
    def _dedup_sector_impacts(sector_impacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        best_by_sector: Dict[str, Dict[str, Any]] = {}
        for impact in sector_impacts:
            if not isinstance(impact, dict):
                continue
            sector = ConductionMapper._clean_text_value(impact.get("sector", ""))
            if not sector:
                continue
            score = 0.0
            try:
                score = float(impact.get("impact_score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            prev = best_by_sector.get(sector)
            if prev is None:
                best_by_sector[sector] = impact
                continue
            try:
                prev_score = float(prev.get("impact_score", 0.0))
            except (TypeError, ValueError):
                prev_score = 0.0
            if score > prev_score:
                best_by_sector[sector] = impact
        return list(best_by_sector.values())

    def _passes_reason_gate(self, candidate: Dict[str, Any], semantic_event_type: str, headline: str) -> bool:
        symbol = str(candidate.get("symbol", "")).strip().upper()
        reason = str(candidate.get("reason", "")).strip().lower()
        if not reason:
            return False
        if symbol not in {"XOM", "CAT"}:
            return True
        if bool(candidate.get("whether_direct_ticker_mentioned", False)):
            return True
        text = self._normalize_text(headline, reason)
        required = ("oil", "原油", "energy", "能源", "opec", "lng", "tariff", "关税", "冲突", "制裁", "shipping", "航运")
        if semantic_event_type in {"energy", "commodity", "geo_political", "monetary"} and any(k in text for k in required):
            return True
        return False

    def _allows_healthcare_in_tier1(self, semantic_output: Optional[Dict[str, Any]], headline: str, summary: str) -> bool:
        text = self._normalize_text(headline, summary)
        if any(hint in text for hint in self._HEALTHCARE_HINTS):
            return True
        if not isinstance(semantic_output, dict):
            return False
        candidates = semantic_output.get("transmission_candidates", [])
        if isinstance(candidates, list):
                merged = ",".join(str(x).lower() for x in candidates)
                if any(hint in merged for hint in self._HEALTHCARE_HINTS):
                    return True
        return False

    def _allows_healthcare_for_event(self, semantic_output: Optional[Dict[str, Any]], headline: str, summary: str) -> bool:
        # Use content-driven allowlist only. Event-type labels can be noisy and
        # should not by themselves route to Healthcare.
        return self._allows_healthcare_in_tier1(semantic_output, headline, summary)

    def _build_template_mapping(self, template: Dict[str, Any], sector_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        levels = template.get("levels", []) or []
        conduction_path = [str(level.get("name", "")) for level in levels if level.get("name")]
        template_id = self._clean_text_value(template.get("id", "")) or "unknown"
        template_name = self._clean_text_value(template.get("name", "")) or "模板链路"

        macro_factors = []
        for item in self._level_items(levels, "macro"):
            macro_factors.append(
                {
                    "factor": self._clean_text_value(item.get("factor")),
                    "direction": self._clean_text_value(item.get("direction")),
                    "strength": self._clean_text_value(item.get("strength")),
                    "reason": f"模板 {template_id} 命中",
                }
            )

        sector_impacts = []
        for item in self._level_items(levels, "sector"):
            sector_impacts.append(
                {
                    "sector": self._clean_text_value(item.get("name")),
                    "direction": self._clean_text_value(item.get("direction")),
                    "driver_type": "template",
                    "reason": f"模板 {template_id} 命中",
                    "impact_score": item.get("impact_score", 0.0),
                }
            )

        stock_candidates = []
        for item in self._level_items(levels, "sector"):
            sector_name = self._normalize_sector_name(item.get("name", ""))
            if sector_name not in self._sector_whitelist:
                continue
            for candidate in sector_data:
                candidate_sector = self._clean_text_value(candidate.get("sector", "")) or self._clean_text_value(candidate.get("industry", ""))
                if not candidate_sector:
                    continue
                candidate_symbol = str(candidate.get("symbol", "")).strip().upper()
                if not self._is_valid_symbol(candidate_symbol):
                    continue
                if sector_name and sector_name.lower() in candidate_sector.lower():
                    stock_candidates.append(
                        {
                            "symbol": candidate_symbol,
                            "sector": self._normalize_sector_name(candidate_sector),
                            "direction": item.get("direction", "benefit"),
                            "event_beta": 1.0,
                            "liquidity_tier": "high",
                            "reason": f"模板 {template_id} 关联",
                            "source": "config",
                        }
                    )

        defaults = self.config_center.get_registered("gate_policy", {}).get("conduction_mapper", {})
        confidence = float(defaults.get("template_base_confidence", 80))
        if template_id == "rate_cut_chain":
            confidence = float(defaults.get("template_rate_cut_confidence", 88))
        elif template_id == "inflation_shock_chain":
            confidence = float(defaults.get("template_inflation_confidence", 82))

        return {
            "macro_factors": macro_factors,
            "asset_impacts": [],
            "sector_impacts": sector_impacts,
            "stock_candidates": stock_candidates,
            "conduction_path": conduction_path or [template_name],
            "confidence": confidence,
            "mapping_source": f"template:{template_id}",
        }

    def _apply_sector_mapping(self, sector_impacts: List[Dict[str, Any]], sector_data: List[Dict[str, Any]]) -> None:
        if not sector_data:
            return
        mapping = self._load_sector_mapping()
        if not mapping:
            return
        available = {
            self._clean_text_value(item.get("sector", "")): item
            for item in sector_data
            if self._clean_text_value(item.get("sector", ""))
        }
        for impact in sector_impacts:
            tag = self._clean_text_value(impact.get("sector", ""))
            candidates = mapping.get(tag, [])
            chosen = ""
            if isinstance(candidates, list):
                for name in candidates:
                    candidate_name = self._clean_text_value(name)
                    if candidate_name in available:
                        chosen = candidate_name
                        break
                if not chosen:
                    for name in candidates:
                        candidate_name = self._clean_text_value(name)
                        if candidate_name:
                            chosen = candidate_name
                            break
            if chosen:
                impact["sector"] = self._normalize_sector_name(chosen)
            else:
                impact["sector"] = self._normalize_sector_name(tag)

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

    def _pr110_contract_cfg(self) -> Dict[str, Any]:
        payload = self.config_center.get_registered("causal_contract_policy", {})
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _enforce_enum(value: str, allowed: List[str], fallback: str) -> str:
        normalized = str(value or "").strip()
        if normalized in allowed:
            return normalized
        return fallback

    def _build_expectation_gap_contract(self, semantic_out: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self._pr110_contract_cfg().get("expectation_gap", {}) or {}
        high = int(self._safe_float(cfg.get("high_threshold"), 25))
        medium = int(self._safe_float(cfg.get("medium_threshold"), 10))
        if "expectation_gap" not in semantic_out:
            return {"value": "unknown", "raw_score": None, "reason": "missing_input"}

        raw_value = semantic_out.get("expectation_gap")
        try:
            raw_gap = int(float(raw_value))
        except (TypeError, ValueError):
            return {"value": "conflict", "raw_score": None, "reason": "invalid_value"}

        abs_gap = abs(raw_gap)
        if raw_gap >= medium:
            value = "positive_surprise"
            reason = "surprise_up"
        elif raw_gap <= -medium:
            value = "negative_surprise"
            reason = "surprise_down"
        else:
            value = "in_line"
            reason = "priced_in"
        if abs_gap >= high:
            reason = f"{reason}_high"
        return {
            "value": value,
            "raw_score": raw_gap,
            "reason": reason,
        }

    @staticmethod
    def _expected_from_relative(direction: str) -> str:
        val = str(direction or "").strip().lower()
        if val in {"benefit", "long", "outperform", "up"}:
            return "up"
        if val in {"hurt", "short", "underperform", "down"}:
            return "down"
        if val in {"watch", "neutral", "flat"}:
            return "flat"
        return "unknown"

    def _build_market_validation_evidence(
        self,
        sector_data: List[Dict[str, Any]],
        sector_impacts: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        cfg = self._pr110_contract_cfg().get("market_validation", {}) or {}
        threshold = self._safe_float(cfg.get("change_pct_confirm_threshold"), 0.10)
        max_items = max(1, int(self._safe_float(cfg.get("max_evidence_items"), 5)))
        evidence: List[Dict[str, Any]] = []
        expected_by_sector: Dict[str, str] = {}
        for impact in sector_impacts:
            sector_name = self._normalize_sector_name(impact.get("sector", ""))
            if not sector_name:
                continue
            expected_by_sector[sector_name] = self._expected_from_relative(str(impact.get("direction", "")))

        confirmed = 0
        contradicted = 0
        for item in sector_data[:max_items]:
            raw_change = item.get("change_pct")
            sector = self._normalize_sector_name(self._resolve_sector_snapshot_name(item))
            if not sector:
                continue
            if raw_change is None:
                evidence.append(
                    {
                        "layer": "sector",
                        "asset": sector,
                        "expected": expected_by_sector.get(sector, "unknown"),
                        "observed": "missing",
                        "status": "not_confirmed",
                        "weight": 0.2,
                        "source": "missing",
                    }
                )
                continue
            change_pct = self._safe_float(raw_change, 0.0)
            expected = expected_by_sector.get(sector, "unknown")
            observed = "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat")
            if abs(change_pct) >= threshold:
                if expected == "unknown":
                    status = "partial"
                elif expected in {"up", "down"} and observed != expected:
                    status = "contradicted"
                    contradicted += 1
                else:
                    status = "confirmed"
                    confirmed += 1
            elif abs(change_pct) == 0:
                status = "not_confirmed"
            else:
                status = "partial"
            evidence.append(
                {
                    "layer": "sector",
                    "asset": sector,
                    "expected": expected,
                    "observed": observed,
                    "status": status,
                    "weight": 0.8,
                    "source": "sector_snapshot",
                }
            )
        if not evidence:
            return "insufficient_data", []
        # PR110 contract: sector snapshot alone cannot produce "validated".
        # Without macro-asset evidence, cap top status at partial/unconfirmed/contradicted.
        has_macro_asset = any(str(x.get("source", "")) == "macro_asset" for x in evidence)
        if contradicted > 0 and confirmed == 0:
            top_status = "contradicted"
        elif confirmed == len(evidence) and has_macro_asset:
            top_status = "validated"
        elif confirmed > 0:
            top_status = "partial"
        else:
            top_status = "unconfirmed"
        return top_status, evidence

    def _build_dominant_driver(
        self,
        semantic_event_type: str,
        mapping: Dict[str, Any],
        market_validation_status: str,
    ) -> Dict[str, Any]:
        dominant_cfg = self._pr110_contract_cfg().get("dominant_driver", {}) or {}
        cfg = dominant_cfg.get("by_event_type", {}) if isinstance(dominant_cfg, dict) else {}
        allowed = dominant_cfg.get("allowed_values", []) if isinstance(dominant_cfg, dict) else []
        allowed = [str(x).strip() for x in allowed if str(x).strip()]
        if market_validation_status in {"insufficient_data", "unconfirmed"}:
            return {"primary": "unknown", "secondary": [], "driver_confidence": 0.0}

        dominant = str(cfg.get(semantic_event_type) or "").strip()
        if not dominant:
            macro = mapping.get("macro_factors", [])
            if isinstance(macro, list) and macro:
                dominant = str((macro[0] or {}).get("factor", "")).strip()
        if not dominant:
            dominant = "unknown"
        if allowed:
            dominant = self._enforce_enum(dominant, allowed, "unknown")
        secondary: List[str] = []
        macro = mapping.get("macro_factors", [])
        if isinstance(macro, list):
            for factor in macro[1:3]:
                name = str((factor or {}).get("factor", "")).strip()
                if name and name != dominant and name not in secondary:
                    secondary.append(self._enforce_enum(name, allowed, "unknown") if allowed else name)
        driver_confidence = 0.8 if market_validation_status == "validated" else 0.6
        if market_validation_status == "contradicted":
            driver_confidence = 0.3
        return {"primary": dominant, "secondary": secondary, "driver_confidence": driver_confidence}

    def _build_relative_absolute_direction_contract(
        self,
        semantic_event_type: str,
        sector_impacts: List[Dict[str, Any]],
    ) -> Tuple[str, str, Dict[str, Any]]:
        contract_cfg = self._pr110_contract_cfg()
        absolute_allowed = contract_cfg.get("absolute_direction", {}).get("allowed_values", [])
        relative_allowed = contract_cfg.get("relative_direction", {}).get("allowed_values", [])
        absolute_allowed = [str(x).strip() for x in absolute_allowed if str(x).strip()]
        relative_allowed = [str(x).strip() for x in relative_allowed if str(x).strip()]
        abs_positive = "positive"
        abs_negative = "negative"
        mapped: List[Dict[str, Any]] = []
        rel_counts = {"outperform": 0, "underperform": 0}
        abs_counts = {"positive": 0, "negative": 0}
        for impact in sector_impacts:
            sector = self._normalize_sector_name(impact.get("sector", ""))
            raw_relative = str(impact.get("direction", "watch")).strip().lower()
            if raw_relative in {"benefit", "long", "up"}:
                relative = "outperform"
                rel_counts["outperform"] += 1
                absolute = abs_positive
                abs_counts["positive"] += 1
            elif raw_relative in {"hurt", "short", "down"}:
                relative = "underperform"
                rel_counts["underperform"] += 1
                absolute = abs_negative
                abs_counts["negative"] += 1
            else:
                relative = "neutral"
                absolute = "unknown"
            if relative_allowed:
                relative = self._enforce_enum(relative, relative_allowed, "unknown")
            if absolute_allowed:
                absolute = self._enforce_enum(absolute, absolute_allowed, "unknown")
            mapped.append(
                {
                    "sector": sector,
                    "relative": relative,
                    "absolute": absolute,
                }
            )
        if rel_counts["outperform"] > rel_counts["underperform"]:
            relative_top = "outperform"
        elif rel_counts["underperform"] > rel_counts["outperform"]:
            relative_top = "underperform"
        else:
            relative_top = "neutral" if mapped else "unknown"

        if abs_counts["positive"] > 0 and abs_counts["negative"] > 0:
            absolute_top = "mixed"
        elif abs_counts["positive"] > 0:
            absolute_top = "positive"
        elif abs_counts["negative"] > 0:
            absolute_top = "negative"
        else:
            absolute_top = "unknown"
        if relative_allowed:
            relative_top = self._enforce_enum(relative_top, relative_allowed, "unknown")
        if absolute_allowed:
            absolute_top = self._enforce_enum(absolute_top, absolute_allowed, "unknown")

        return relative_top, absolute_top, {
            "event_type": semantic_event_type,
            "sectors": mapped,
        }

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
            raw_change_pct = item.get("change_pct", None)
            change_pct = None
            if raw_change_pct is not None:
                change_pct = self._safe_float(raw_change_pct, 0.0)
                # Skip near-flat moves to reduce noise when a live delta exists.
                if abs(change_pct) < 0.1:
                    continue
                direction = "benefit" if change_pct >= 0 else "hurt"
                reason = f"实时ETF变化 {change_pct:+.2f}%"
            else:
                direction = "benefit"
                reason = "实时ETF快照映射"
            sector_name = self._normalize_sector_name(self._resolve_sector_snapshot_name(item))
            if not sector_name or sector_name not in self._sector_whitelist:
                continue
            impact = {
                "sector": sector_name,
                "direction": direction,
                "driver_type": "market_validation",
                "reason": reason,
            }
            if change_pct is not None:
                impact["change_pct"] = round(change_pct, 2)
            sector_impacts.append(impact)

        stock_candidates: List[Dict[str, Any]] = []
        for impact in sector_impacts[:2]:
            direction = "long" if impact.get("direction") == "benefit" else "short"
            impact_sector = self._normalize_sector_name(impact.get("sector", ""))
            for item in sector_data:
                candidate_sector = self._normalize_sector_name(self._resolve_sector_snapshot_name(item))
                symbol = str(item.get("symbol", "")).strip().upper()
                if candidate_sector != impact_sector or not self._is_valid_symbol(symbol):
                    continue
                stock_candidates.append(
                    {
                        "symbol": symbol,
                        "sector": impact_sector,
                        "direction": direction,
                        "event_beta": 0.9,
                        "liquidity_tier": "high",
                        "reason": impact.get("reason", "实时板块映射"),
                    }
                )
                break

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
        headline = self._clean_text_value(raw.get("headline", ""))
        summary = self._clean_text_value(raw.get("summary", ""))
        policy_intervention = raw.get("policy_intervention", "NONE")
        sector_data = raw.get("sector_data", []) or []

        if not headline and not summary:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "INSUFFICIENT_EVENT_CONTEXT", "message": "Headline or summary is required"}],
            )

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

        semantic_event_type = str(semantic_out.get("event_type", "")).strip().lower()
        semantic_subtype = self._extract_subtype(semantic_event_type, headline, summary, semantic_out)
        sector_weight_view = self._build_sector_weight_view(
            semantic_event_type=semantic_event_type,
            subtype=semantic_subtype,
            headline=headline,
            summary=summary,
            semantic_output=semantic_out,
            sector_impacts=mapping.get("sector_impacts", []),
        )
        healthcare_allowed = self._allows_healthcare_for_event(semantic_out, headline, summary)
        if not healthcare_allowed:
            mapping["sector_impacts"] = [
                impact for impact in mapping.get("sector_impacts", [])
                if self._normalize_sector_name(impact.get("sector", "")).lower() != "healthcare"
            ]

        if semantic_event_type in self._TIER1_EVENT_TYPES and not self._allows_healthcare_in_tier1(semantic_out, headline, summary):
            mapping["sector_impacts"] = [
                impact for impact in mapping.get("sector_impacts", [])
                if self._normalize_sector_name(impact.get("sector", "")).lower() != "healthcare"
            ]

        semantic_stock_candidates = self._build_semantic_stock_candidates(
            semantic_output=semantic_out,
            sector_impacts=mapping.get("sector_impacts", []),
        )
        pool_stock_candidates = self._build_ticker_pool_candidates(
            semantic_output=semantic_out,
            subtype=semantic_subtype,
            sector_weight_view=sector_weight_view,
            sector_impacts=mapping.get("sector_impacts", []),
        )
        recommendation_buckets = self._split_recommendation_buckets(
            semantic_event_type=semantic_event_type,
            headline=headline,
            candidates=pool_stock_candidates,
        )
        mapping["stock_candidates"] = self._merge_stock_candidates(
            base_candidates=list(mapping.get("stock_candidates", [])),
            semantic_candidates=semantic_stock_candidates + recommendation_buckets.get("recommended", []) + recommendation_buckets.get("watchlist", []),
        )

        original_sector_impacts = [dict(impact) for impact in mapping.get("sector_impacts", [])]
        mapping["sector_impacts"] = [
            impact
            for impact in mapping.get("sector_impacts", [])
            if self._normalize_sector_name(impact.get("sector", "")) in self._sector_whitelist
        ]
        for impact in mapping["sector_impacts"]:
            impact["sector"] = self._normalize_sector_name(impact.get("sector", ""))
        mapping["sector_impacts"] = self._dedup_sector_impacts(mapping.get("sector_impacts", []))

        # Tier1: override sector_impacts from computed sector_weight_view so that
        # sector_candidates in trace_scorecard reflects the Tier1-weighted sectors.
        # Direction inherits from original template impact if available; default watch.
        tier1_override_audit = None
        if semantic_event_type in self._TIER1_EVENT_TYPES and sector_weight_view.get("sector_weights"):
            orig_directions = {}
            for imp in mapping.get("sector_impacts", []):
                s = self._normalize_sector_name(imp.get("sector", ""))
                if s:
                    orig_directions[s] = imp.get("direction", "watch")
            tier1_impacts = []
            provenance: List[Dict[str, Any]] = []
            for sector_name, weight in sector_weight_view["sector_weights"].items():
                ns = self._normalize_sector_name(sector_name)
                direction = orig_directions.get(ns, "watch")
                provenance.append(
                    {
                        "sector": ns,
                        "direction": direction,
                        "impact_score": weight,
                    }
                )
                tier1_impacts.append({
                    "sector": sector_name,
                    "direction": direction,
                    "driver_type": "tier1_weight",
                    "impact_score": weight,
                    "reason": f"Tier1 weight {weight:.2f}",
                })
            mapping["sector_impacts"] = tier1_impacts
            tier1_override_audit = {
                "override_reason": "tier1_weighted_sector_override",
                "original_count": len(original_sector_impacts),
                "overridden_count": len(original_sector_impacts),
                "original_provenance": original_sector_impacts,
                "retained_count": len(tier1_impacts),
                "weighted_provenance": provenance,
            }

        mapping["stock_candidates"] = [
            cand
            for cand in mapping.get("stock_candidates", [])
            if self._is_valid_symbol(cand.get("symbol")) and self._normalize_sector_name(cand.get("sector", "")) in self._sector_whitelist
        ]
        if semantic_event_type in self._TIER1_EVENT_TYPES and not self._allows_healthcare_in_tier1(semantic_out, headline, summary):
            mapping["stock_candidates"] = [
                cand for cand in mapping.get("stock_candidates", [])
                if self._normalize_sector_name(cand.get("sector", "")).lower() != "healthcare"
            ]
        if not healthcare_allowed:
            mapping["stock_candidates"] = [
                cand for cand in mapping.get("stock_candidates", [])
                if self._normalize_sector_name(cand.get("sector", "")).lower() != "healthcare"
            ]
        for cand in mapping["stock_candidates"]:
            cand["symbol"] = str(cand.get("symbol", "")).strip().upper()
            cand["sector"] = self._normalize_sector_name(cand.get("sector", ""))
        title_text = self._normalize_text(headline)
        if any(h in title_text for h in self._ASIA_TECH_HINTS):
            mapping["stock_candidates"] = [
                cand
                for cand in mapping.get("stock_candidates", [])
                if str(cand.get("symbol", "")).strip().upper() not in self._ENERGY_TICKERS
            ]
        non_us_hint = any(h in title_text for h in self._NON_US_MARKET_HINTS)
        geo_energy_allowed = any(h in title_text for h in self._GEO_ENERGY_ALLOWED_HINTS)
        if non_us_hint and not geo_energy_allowed:
            mapping["stock_candidates"] = [
                cand
                for cand in mapping.get("stock_candidates", [])
                if str(cand.get("symbol", "")).strip().upper() not in self._ENERGY_TICKERS
            ]
        if non_us_hint:
            mapping["stock_candidates"] = [
                cand
                for cand in mapping.get("stock_candidates", [])
                if str(cand.get("symbol", "")).strip().upper() not in self._NON_US_BLOCK_PROXY_TICKERS
            ]
        if non_us_hint and semantic_event_type == "other":
            mapping["stock_candidates"] = [
                cand
                for cand in mapping.get("stock_candidates", [])
                if str(cand.get("symbol", "")).strip().upper() not in self._US_TECH_FIN_PROXY_TICKERS
            ]
        mapping["stock_candidates"] = [
            cand
            for cand in mapping.get("stock_candidates", [])
            if self._passes_reason_gate(cand, semantic_event_type, headline)
        ]

        needs_manual_review = not (mapping["macro_factors"] and mapping["sector_impacts"] and mapping["stock_candidates"])
        expectation_gap_contract = self._build_expectation_gap_contract(semantic_out if isinstance(semantic_out, dict) else {})
        market_validation_status, market_validation_evidence = self._build_market_validation_evidence(
            sector_data,
            mapping.get("sector_impacts", []),
        )
        dominant_driver = self._build_dominant_driver(semantic_event_type, mapping, market_validation_status)
        relative_direction, absolute_direction, direction_contract = self._build_relative_absolute_direction_contract(
            semantic_event_type=semantic_event_type,
            sector_impacts=mapping.get("sector_impacts", []),
        )
        macro_factors = mapping.get("macro_factors", [])
        macro_factor = {}
        macro_policy = self._pr110_contract_cfg().get("macro_factor", {}) or {}
        macro_factor_allowed = [str(x).strip() for x in (macro_policy.get("factor_allowed_values", []) or []) if str(x).strip()]
        macro_direction_allowed = [str(x).strip() for x in (macro_policy.get("direction_allowed_values", []) or []) if str(x).strip()]
        macro_strength_allowed = [str(x).strip() for x in (macro_policy.get("strength_allowed_values", []) or []) if str(x).strip()]
        if isinstance(macro_factors, list) and macro_factors:
            primary_macro = macro_factors[0] or {}
            factor = str(primary_macro.get("factor", "")).strip() or "unknown"
            direction = str(primary_macro.get("direction", "")).strip() or "unknown"
            strength = str(primary_macro.get("strength", "")).strip() or "unknown"
            if macro_factor_allowed:
                factor = self._enforce_enum(factor, macro_factor_allowed, "unknown")
            if macro_direction_allowed:
                direction = self._enforce_enum(direction, macro_direction_allowed, "unknown")
            if macro_strength_allowed:
                strength = self._enforce_enum(strength, macro_strength_allowed, "unknown")
            macro_factor = {
                "factor": factor,
                "direction": direction,
                "strength": strength,
            }
        else:
            macro_factor = {"factor": "unknown", "direction": "unknown", "strength": "unknown"}

        impact_layers = ["macro", "sector", "ticker"] if mapping.get("stock_candidates") else ["macro", "sector"]
        layer_allowed = [str(x).strip() for x in (self._pr110_contract_cfg().get("impact_layers", {}).get("allowed_values", []) or []) if str(x).strip()]
        if layer_allowed:
            impact_layers = [x for x in impact_layers if x in layer_allowed]
            if not impact_layers:
                impact_layers = ["macro"]
        validation_confidence = min(1.0, max(0.0, len([x for x in market_validation_evidence if x.get("status") == "confirmed"]) / 3.0))
        causal_confidence = self._normalize_confidence_value(mapping.get("confidence", 0.0), 0.0)
        causal_contract = {
            "expectation_gap": expectation_gap_contract,
            "macro_factor": macro_factor,
            "market_validation": {
                "status": market_validation_status,
                "evidence": market_validation_evidence,
            },
            "dominant_driver": dominant_driver,
            "relative_direction": relative_direction,
            "absolute_direction": absolute_direction,
            "impact_layers": impact_layers,
            "confidence": {
                "causal_confidence": round(causal_confidence, 4),
                "validation_confidence": round(validation_confidence, 4),
            },
        }

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
                "semantic_event_type": semantic_event_type,
                "semantic_subtype": semantic_subtype,
                "sector_weights": sector_weight_view.get("sector_weights", {}),
                "primary_sector": sector_weight_view.get("primary_sector", ""),
                "secondary_sectors": sector_weight_view.get("secondary_sectors", []),
                "sector_weight_quality_score": sector_weight_view.get("weight_quality_score", 0.0),
                "stock_recommendation_buckets": recommendation_buckets,
                "time_horizons": {
                    "intraday": "headline冲击主导",
                    "overnight": "等待二次验证",
                    "multiweek": "确认后转向基本面传导",
                },
                "conduction_path": mapping["conduction_path"],
                "confidence": mapping["confidence"],
                "needs_manual_review": needs_manual_review,
                "mapping_source": mapping.get("mapping_source", "rule"),
                "causal_contract": causal_contract,
                "expectation_gap": expectation_gap_contract,
                "macro_factor": macro_factor,
                "market_validation": {
                    "status": market_validation_status,
                    "evidence": market_validation_evidence,
                },
                "dominant_driver": dominant_driver,
                "relative_direction": relative_direction,
                "absolute_direction": absolute_direction,
                "impact_layers": impact_layers,
                "confidence_contract": causal_contract["confidence"],
                "expectation_gap_contract": expectation_gap_contract,
                "market_validation_evidence": market_validation_evidence,
                "direction_contract": direction_contract,
                "audit": {
                    "module": self.name,
                    "rule_version": "conduction_v1",
                    "decision_trace": mapping["conduction_path"],
                    "tier1_sector_override": tier1_override_audit,
                    "candidate_drop_diagnostics": recommendation_buckets.get("drop_diagnostics", []),
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
