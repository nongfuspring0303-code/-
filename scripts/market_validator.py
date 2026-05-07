#!/usr/bin/env python3
"""
MarketValidator for EDT analysis layer.

This module scores whether the market is validating the mapped event logic
through price, volume, linkage, persistence, and dispersion.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class MarketValidator(EDTModule):
    """Market validation scorer."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("MarketValidator", "1.0.0", config_path)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["event_id", "conduction_output", "market_timestamp"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    @staticmethod
    def _normalize_macro_confirmation(value: Any) -> str:
        v = str(value or "").strip().lower()
        if v in {"supportive", "neutral", "hostile"}:
            return v
        return ""

    @staticmethod
    def _normalize_sector_confirmation(value: Any) -> str:
        v = str(value or "").strip().lower()
        if v in {"strong", "medium", "weak", "none"}:
            return v
        return ""

    @staticmethod
    def _normalize_leader_confirmation(value: Any) -> str:
        v = str(value or "").strip().lower()
        if v in {"confirmed", "partial", "unconfirmed", "failed"}:
            return v
        return ""

    @staticmethod
    def _legacy_state_from_a1(a1: int, linkage_confirmed: Any, price_score: int) -> str:
        if a1 >= 80:
            return "validated"
        if a1 >= 60:
            return "partially_validated"
        if linkage_confirmed is False and price_score > 0:
            return "not_validated"
        return "counter_validated" if a1 < 20 else "not_validated"

    def _derive_confirmations(self, raw: Dict[str, Any], a1: int) -> Dict[str, Any]:
        macro = self._normalize_macro_confirmation(raw.get("macro_confirmation"))
        sector = self._normalize_sector_confirmation(raw.get("sector_confirmation"))
        leader = self._normalize_leader_confirmation(raw.get("leader_confirmation"))

        if not macro:
            regime = str(raw.get("macro_regime", "")).strip().upper()
            if regime == "RISK_OFF":
                macro = "hostile"
            elif regime == "RISK_ON":
                macro = "supportive"
            else:
                macro = "supportive" if a1 >= 70 else "neutral"

        if not sector:
            if a1 >= 80:
                sector = "strong"
            elif a1 >= 60:
                sector = "medium"
            elif a1 >= 35:
                sector = "weak"
            else:
                sector = "none"

        if not leader:
            leader_move = float(raw.get("leader_price_change_pct", 0) or 0)
            leader_vol = float(raw.get("leader_volume_ratio", 0) or 0)
            if leader_move >= 1.5 and leader_vol >= 1.5:
                leader = "confirmed"
            elif leader_move >= 0.5:
                leader = "partial"
            elif leader_move <= -0.8:
                leader = "failed"
            else:
                leader = "unconfirmed"

        if macro == "hostile" or sector == "none" or leader == "failed" or a1 < 35:
            a1_validation = "fail"
        elif macro == "supportive" and sector in {"strong", "medium"} and leader in {"confirmed", "partial"} and a1 >= 60:
            a1_validation = "pass"
        else:
            a1_validation = "partial"

        positive_signals = []
        negative_signals = []
        if macro == "supportive":
            positive_signals.append("macro_supportive")
        if sector in {"strong", "medium"}:
            positive_signals.append(f"sector_{sector}")
        if leader in {"confirmed", "partial"}:
            positive_signals.append(f"leader_{leader}")

        if macro == "hostile":
            negative_signals.append("macro_hostile")
        if sector in {"weak", "none"}:
            negative_signals.append(f"sector_{sector}")
        if leader in {"unconfirmed", "failed"}:
            negative_signals.append(f"leader_{leader}")
        if a1_validation == "fail":
            negative_signals.append("a1_fail_gate")

        reason_text = (
            f"macro={macro}, sector={sector}, leader={leader}, "
            f"a1_validation={a1_validation}, a1_score={a1}"
        )
        return {
            "macro_confirmation": macro,
            "sector_confirmation": sector,
            "leader_confirmation": leader,
            "a1_market_validation": a1_validation,
            "positive_signals": positive_signals,
            "negative_signals": negative_signals,
            "reason_text": reason_text,
        }

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        conduction_output = raw.get("conduction_output", {})

        if not conduction_output:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "MISSING_CONDUCTION_CONTEXT", "message": "Missing conduction output"}],
            )

        price_changes = raw.get("price_changes", {})
        volume_changes = raw.get("volume_changes", {})
        if not isinstance(price_changes, dict):
            price_changes = {}
        if not isinstance(volume_changes, dict):
            volume_changes = {}
        missing_market_data = not price_changes and not volume_changes

        linkage = raw.get("cross_asset_linkage", {})
        if not isinstance(linkage, dict):
            linkage = {}
        persistence_minutes = float(raw.get("persistence_minutes", 0))
        dispersion = raw.get("winner_loser_dispersion", {})
        if not isinstance(dispersion, dict):
            dispersion = {}
        market_data_source = str(raw.get("market_data_source", "unknown")).strip().lower() or "unknown"
        market_data_present = bool(raw.get("market_data_present", bool(price_changes or volume_changes)))
        market_data_stale = bool(raw.get("market_data_stale", False))
        market_data_default_used = bool(raw.get("market_data_default_used", False))
        market_data_fallback_used = bool(raw.get("market_data_fallback_used", False))

        price_score = 20 if any(abs(v) >= 0.8 for v in price_changes.values()) else 5
        volume_score = 15 if any(v >= 1.4 for v in volume_changes.values()) else 0
        linkage_score = 20 if linkage.get("confirmed") else 0
        persistence_score = 25 if persistence_minutes >= 60 else (15 if persistence_minutes >= 30 else 0)
        divergence_score = 20 if dispersion.get("confirmed") else 0

        a1 = price_score + volume_score + linkage_score + persistence_score + divergence_score

        failed_checks = []
        if missing_market_data:
            failed_checks.append("missing_market_data")
        if price_score < 20:
            failed_checks.append("price_confirmation")
        if volume_score < 15:
            failed_checks.append("volume_confirmation")
        if linkage_score < 20:
            failed_checks.append("cross_asset_linkage")
        if persistence_score < 25:
            failed_checks.append("persistence")
        if divergence_score < 20:
            failed_checks.append("winner_loser_divergence")

        # DEEP AUDIT: Enforcement of MEMORY.md L176 (Multi-source check for high volatility)
        max_abs_move = max([abs(v) for v in price_changes.values()] + [0])
        needs_multi_source = False
        if max_abs_move >= 5.0:
            needs_multi_source = True
            source_count_required = 3
        elif max_abs_move >= 3.0:
            needs_multi_source = True
            source_count_required = 2
        else:
            source_count_required = 1

        # Current implementation only has single source from Yahoo via payloader
        multi_source_confirmed = (not needs_multi_source) or (market_data_source == "multi_verified")
        if needs_multi_source and not multi_source_confirmed:
            failed_checks.append(f"multi_source_verification_required_{source_count_required}")
            a1 = int(a1 * 0.7) # Penalty for unverified high volatility

        if a1 >= 80:
            state = "validated"
        elif a1 >= 60:
            state = "partially_validated"
        elif linkage.get("confirmed") is False and price_score > 0:
            state = "not_validated"
        else:
            state = "counter_validated" if a1 < 20 else "not_validated"
        confirmations = self._derive_confirmations(raw, a1)
        state = self._legacy_state_from_a1(a1, linkage.get("confirmed"), price_score)

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "event_id": raw["event_id"],
                "price_score": price_score,
                "volume_score": volume_score,
                "linkage_score": linkage_score,
                "persistence_score": persistence_score,
                "divergence_score": divergence_score,
                "A1": a1,
                "validation_state": state,
                "failed_checks": failed_checks,
                "validation_notes": "市场验证按价格、量能、联动、持续性、分化五项计算",
                "market_data_source": market_data_source,
                "market_data_present": market_data_present,
                "market_data_stale": market_data_stale,
                "market_data_default_used": market_data_default_used,
                "market_data_fallback_used": market_data_fallback_used,
                **confirmations,
                "needs_manual_review": False,
                "audit": {
                    "module": self.name,
                    "rule_version": "validation_v1",
                    "decision_trace": [price_score, volume_score, linkage_score, persistence_score, divergence_score],
                },
            },
        )


if __name__ == "__main__":
    payload = {
        "event_id": "ME-C-20260330-001.V1.0",
        "conduction_output": {"conduction_path": ["关税升级", "通胀压力上升"]},
        "price_changes": {"DXY": 1.2, "XLI": -1.8},
        "volume_changes": {"XLI": 2.3},
        "cross_asset_linkage": {"confirmed": True},
        "persistence_minutes": 90,
        "winner_loser_dispersion": {"confirmed": True},
        "market_timestamp": "2026-03-30T15:00:00Z",
    }
    print(MarketValidator().run(payload).data)
