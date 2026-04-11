#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict

from .sector_ranker import rank_sectors
from .state_machine import evaluate_state
from .stock_exposure_model import build_stock_candidates


def build_trade_decision(event_payload: Dict[str, Any], gate_policy: Dict[str, Any]) -> Dict[str, Any]:
    sectors = event_payload.get("sectors", []) or []
    sector_rankings = event_payload.get("sector_rankings") or rank_sectors(sectors)
    max_candidates = int(((gate_policy.get("signal_grade") or {}).get("max_stock_candidates") or 5))
    stock_candidates = event_payload.get("stock_candidates") or build_stock_candidates(
        event_payload,
        sector_rankings,
        max_candidates=max_candidates,
    )

    enriched = dict(event_payload)
    enriched["sector_rankings"] = sector_rankings
    enriched["stock_candidates"] = stock_candidates

    state = evaluate_state(enriched, gate_policy)
    out = dict(event_payload)
    out["sector_rankings"] = sector_rankings
    out["stock_candidates"] = stock_candidates
    out.update(state)
    return out
