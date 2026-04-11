#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict


def evaluate_state(event: Dict[str, Any], gate_policy: Dict[str, Any]) -> Dict[str, str]:
    required = ["trace_id", "schema_version", "news_timestamp"]
    for key in required:
        if not event.get(key):
            return {
                "action": "NO_ACTION",
                "state_machine_step": "data_integrity",
                "gate_reason_code": "MISSING_FIELDS",
                "gate_reason": f"missing required field: {key}",
            }

    if bool(event.get("mixed_regime", False)):
        override_cfg = (gate_policy.get("mixed_regime_override") or {})
        if not bool(override_cfg.get("enabled", False)):
            return {
                "action": "WATCH",
                "state_machine_step": "mixed_regime",
                "gate_reason_code": "MIXED_REGIME",
                "gate_reason": "mixed_regime with override disabled",
            }
        av_score = float(((event.get("asset_validation") or {}).get("score") or 0.0))
        pd_score = float(((event.get("path_dominance") or {}).get("score") or 0.0))
        sector_gap = float(event.get("sector_top1_top2_gap", 0.0) or 0.0)
        av_min = float((override_cfg.get("asset_validation_min") or 75.0))
        pd_min = float((override_cfg.get("path_dominance_min") or 75.0))
        gap_min = float((override_cfg.get("sector_gap_min") or 15.0))
        if av_score < av_min or pd_score < pd_min or sector_gap < gap_min:
            return {
                "action": "WATCH",
                "state_machine_step": "mixed_regime",
                "gate_reason_code": "MIXED_REGIME",
                "gate_reason": "mixed_regime override conditions not met",
            }

    av = float(((event.get("asset_validation") or {}).get("score") or 0.0))
    av_min = float(((gate_policy.get("asset_validation") or {}).get("trade_min") or 65.0))
    if av < av_min:
        return {
            "action": "WATCH",
            "state_machine_step": "asset_validation",
            "gate_reason_code": "ASSET_UNCONFIRMED",
            "gate_reason": "asset validation below trade_min",
        }

    blocked = bool(event.get("risk_blocked", False))
    if blocked:
        return {
            "action": "NO_ACTION",
            "state_machine_step": "risk_gate",
            "gate_reason_code": "RISK_BLOCKED",
            "gate_reason": "risk gate blocked",
        }

    return {
        "action": "TRADE",
        "state_machine_step": "trade_admission",
        "gate_reason_code": "ALL_PASSED",
        "gate_reason": "all admission gates passed",
    }
