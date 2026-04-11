#!/usr/bin/env python3
"""
Member B asset validation layer.

This module validates asset baskets, preserves whitelist discipline, and
produces a market-adjusted macro_factor_vector from raw macro factors.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence

from scripts.config_center import ConfigCenter
from scripts.edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class AssetValidator(EDTModule):
    """Validate asset baskets and derive market-adjusted macro factors."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("AssetValidator", "1.0.0", config_path)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.asset_basket_path = self.repo_root / "configs" / "asset_baskets.yaml"
        self.gate_policy_path = self.repo_root / "configs" / "gate_policy.yaml"
        self.metric_dictionary_path = self.repo_root / "configs" / "metric_dictionary.yaml"
        self.backtest_protocol_path = self.repo_root / "configs" / "backtest_protocol.yaml"
        self.config_center = ConfigCenter(config_path=config_path)
        self.config_center.register("asset_baskets", self.asset_basket_path)
        self.config_center.register("gate_policy", self.gate_policy_path)
        self.config_center.register("metric_dictionary", self.metric_dictionary_path)
        self.config_center.register("backtest_protocol", self.backtest_protocol_path)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        raw = input_data.get("raw_macro_factor_vector")
        if raw is None:
            return False, "Missing required field: raw_macro_factor_vector"
        if not isinstance(raw, dict):
            return False, "raw_macro_factor_vector must be an object"
        return True, None

    def _bundle(self) -> Dict[str, Any]:
        bundle = self.config_center.get_registered("asset_baskets", {})
        return bundle if isinstance(bundle, dict) else {}

    def _gate_policy(self) -> Dict[str, Any]:
        policy = self.config_center.get_registered("gate_policy", {})
        return policy if isinstance(policy, dict) else {}

    def _metric_dictionary(self) -> Dict[str, Any]:
        metrics = self.config_center.get_registered("metric_dictionary", {})
        return metrics if isinstance(metrics, dict) else {}

    def _backtest_protocol(self) -> Dict[str, Any]:
        protocol = self.config_center.get_registered("backtest_protocol", {})
        return protocol if isinstance(protocol, dict) else {}

    @staticmethod
    def _round(value: Any, precision: int) -> float:
        try:
            return round(float(value), precision)
        except (TypeError, ValueError):
            return round(0.0, precision)

    @staticmethod
    def _clip(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def _normalize_sequence(items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _asset_name(item: Dict[str, Any]) -> str:
        return str(item.get("symbol") or item.get("asset") or item.get("name") or "").strip()

    def _whitelist(self) -> List[str]:
        asset_universe = self._bundle().get("asset_universe", {})
        whitelist = asset_universe.get("whitelist", []) if isinstance(asset_universe, dict) else []
        if isinstance(whitelist, list):
            return [str(item).strip() for item in whitelist if str(item).strip()]
        return []

    def _asset_profiles(self) -> Dict[str, Dict[str, Any]]:
        profiles = self._bundle().get("asset_profiles", {})
        return {str(name): value for name, value in profiles.items() if isinstance(value, dict)} if isinstance(profiles, dict) else {}

    def _basket_defs(self) -> Dict[str, Dict[str, Any]]:
        baskets = self._bundle().get("asset_baskets", {})
        return {str(name): value for name, value in baskets.items() if isinstance(value, dict)} if isinstance(baskets, dict) else {}

    def _score_asset(self, raw_vector: Dict[str, float], profile: Dict[str, Any], precision: int) -> float:
        weights = profile.get("weights", {})
        scale = float(profile.get("score_scale", 0.6))
        weighted_sum = 0.0
        if isinstance(weights, dict):
            for factor, weight in weights.items():
                weighted_sum += float(raw_vector.get(factor, 0.0)) * float(weight)
        base = 50.0 + weighted_sum * scale
        return self._round(self._clip(base, 0.0, 100.0), precision)

    def _score_basket(self, raw_vector: Dict[str, float], basket: Dict[str, Any], precision: int) -> float:
        weights = basket.get("weights", {})
        scale = float(basket.get("score_scale", 0.35))
        weighted_sum = 0.0
        if isinstance(weights, dict):
            for factor, weight in weights.items():
                weighted_sum += float(raw_vector.get(factor, 0.0)) * float(weight)
        base = 50.0 + weighted_sum * scale
        return self._round(self._clip(base, 0.0, 100.0), precision)

    def _build_notes(self, input_data: Dict[str, Any], whitelist: Sequence[str]) -> List[str]:
        notes: List[str] = []
        for item in self._normalize_sequence(input_data.get("candidate_assets") or input_data.get("asset_candidates")):
            asset_name = self._asset_name(item)
            if asset_name and asset_name not in whitelist:
                notes.append(f"Ignored non-whitelist asset: {asset_name}")
        return notes

    def _validation_multiplier(self, validation_score: float) -> float:
        policy = self._gate_policy().get("asset_validation", {})
        market_cfg = policy.get("market_validation", {})
        scale = float(market_cfg.get("scale", 0.20))
        multiplier = 1.0 + ((validation_score - 50.0) / 100.0) * scale
        lower = float(market_cfg.get("multiplier_min", 0.85))
        upper = float(market_cfg.get("multiplier_max", 1.15))
        return self._clip(multiplier, lower, upper)

    def _build_macro_factor_vector(
        self,
        raw_vector: Dict[str, float],
        validation_score: float,
        precision: int,
    ) -> Dict[str, float]:
        multiplier = self._validation_multiplier(validation_score)
        macro_cfg = self._gate_policy().get("asset_validation", {}).get("macro_validation", {})
        lower = float(macro_cfg.get("clip_min", -100.0))
        upper = float(macro_cfg.get("clip_max", 100.0))
        adjusted: Dict[str, float] = {}
        for factor, raw_value in raw_vector.items():
            adjusted[factor] = self._round(self._clip(float(raw_value) * multiplier, lower, upper), precision)
        return adjusted

    def _divergence_penalty(self, divergence_count: int) -> float:
        policy = self._gate_policy().get("asset_validation", {})
        cfg = policy.get("divergence_penalty", {})
        trigger_count = int(cfg.get("trigger_count", 3))
        per_extra = float(cfg.get("per_extra_divergence", 5.0))
        max_penalty = float(cfg.get("max_penalty", 20.0))
        if divergence_count < trigger_count:
            return 0.0
        penalty = (divergence_count - trigger_count + 1) * per_extra
        return self._clip(penalty, 0.0, max_penalty)

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        raw_vector = raw.get("raw_macro_factor_vector", {})
        if not isinstance(raw_vector, dict):
            raw_vector = {}

        precision = int(self._metric_dictionary().get("standards", {}).get("default_rounding_decimals", 2))
        whitelist = self._whitelist()
        profiles = self._asset_profiles()
        baskets = self._basket_defs()
        policy = self._gate_policy().get("asset_validation", {})

        basket_scores = {
            basket_name: self._score_basket(raw_vector, basket_cfg, precision)
            for basket_name, basket_cfg in baskets.items()
        }
        basket_avg = self._round(mean(basket_scores.values()) if basket_scores else 0.0, precision)

        asset_scores: Dict[str, float] = {}
        for asset_name in whitelist:
            profile = profiles.get(asset_name, {})
            asset_scores[asset_name] = self._score_asset(raw_vector, profile, precision)

        ranked_assets = sorted(asset_scores.items(), key=lambda item: item[1], reverse=True)
        leader_min_count = max(1, int(policy.get("leader_min_count", 1)))
        leaders = [name for name, _score in ranked_assets[:leader_min_count]]
        leader_avg = self._round(mean(score for _name, score in ranked_assets[:leader_min_count]) if ranked_assets else 0.0, precision)
        divergences = [name for name, score in ranked_assets if score < float(policy.get("no_action_max", 45.0))]

        basket_weight = float(self._gate_policy().get("trade_admission", {}).get("asset_validation_min", 65.0)) / 100.0
        leader_weight = 1.0 - basket_weight
        penalty = self._divergence_penalty(len(divergences))
        validation_score = basket_avg * basket_weight + leader_avg * leader_weight - penalty
        validation_score = self._round(self._clip(validation_score, 0.0, 100.0), precision)

        trade_min = float(policy.get("trade_min", 65.0))
        no_action_max = float(policy.get("no_action_max", 45.0))
        if validation_score >= trade_min:
            status = "confirmed"
        elif validation_score >= no_action_max:
            status = "divergent"
        else:
            status = "unconfirmed"

        asset_validation = {
            "score": validation_score,
            "status": status,
            "leaders": leaders,
            "divergences": divergences,
            "basket_scores": basket_scores,
        }

        notes = self._build_notes(raw, whitelist)
        macro_factor_vector = self._build_macro_factor_vector(raw_vector, validation_score, precision)

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "event_id": raw.get("event_id"),
                "schema_version": raw.get("schema_version", "v1.1"),
                "asset_validation": asset_validation,
                "macro_factor_vector": macro_factor_vector,
                "notes": notes,
            },
            metadata={
                "config_sections": ["gate_policy", "metric_dictionary", "backtest_protocol", "asset_baskets"],
                "backtest_required": self._backtest_protocol().get("pit_snapshots", {}).get("required", []),
                "whitelist_size": len(whitelist),
                "divergence_penalty_applied": penalty,
            },
        )
