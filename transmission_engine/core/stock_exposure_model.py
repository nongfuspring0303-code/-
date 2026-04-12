#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from scripts.config_center import ConfigCenter


def _root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_premium_pool(pool_path: Path | None = None) -> Dict[str, Dict[str, Any]]:
    path = pool_path or (_root() / "configs" / "premium_stock_pool.yaml")
    cfg_center = ConfigCenter()
    cfg_center.register("premium_stock_pool", path)
    cfg = cfg_center.get_registered("premium_stock_pool", {})
    if not isinstance(cfg, dict):
        cfg = {}
    out: Dict[str, Dict[str, Any]] = {}
    for item in cfg.get("stocks", []):
        symbol = str(item.get("symbol", "")).strip().upper()
        if symbol:
            out[symbol] = item
    return out


def load_event_exposure_matrix(matrix_path: Path | None = None) -> Dict[str, Dict[str, float]]:
    path = matrix_path or (_root() / "configs" / "event_exposure_matrix.yaml")
    cfg_center = ConfigCenter()
    cfg_center.register("event_exposure_matrix", path)
    cfg = cfg_center.get_registered("event_exposure_matrix", {})
    if not isinstance(cfg, dict):
        cfg = {}
    matrix = cfg.get("matrix", {})
    out: Dict[str, Dict[str, float]] = {}
    for symbol, mapping in matrix.items():
        if not isinstance(mapping, dict):
            continue
        out[str(symbol).upper()] = {str(k): _safe_float(v, 50.0) for k, v in mapping.items()}
    return out


def _load_gate_policy() -> Dict[str, Any]:
    cfg = ConfigCenter()
    path = _root() / "configs" / "gate_policy.yaml"
    try:
        cfg.register("gate_policy", path)
        payload = cfg.get_registered("gate_policy", {})
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def build_stock_candidates(
    event_payload: Dict[str, Any],
    sector_rankings: Dict[str, Any],
    max_candidates: int = 5,
) -> List[Dict[str, Any]]:
    premium = load_premium_pool()
    exposure_matrix = load_event_exposure_matrix()
    gate_policy = _load_gate_policy()
    cls_cfg = (gate_policy.get("stock_exposure") or {}).get("classification", {})
    first_order_min = _safe_float(cls_cfg.get("first_order_min", 85.0), 85.0)
    leveraged_proxy_min = _safe_float(cls_cfg.get("leveraged_proxy_min", 65.0), 65.0)

    event_type_lv2 = str(event_payload.get("event_type_lv2", "")).strip()
    primary_sector = str((sector_rankings or {}).get("primary_sector", "")).strip()

    seeded = event_payload.get("stock_candidates", []) or []
    selected: List[Dict[str, Any]] = []
    seen = set()

    def _score(sym: str, seed: Dict[str, Any]) -> Dict[str, Any]:
        s = premium[sym]
        event_exposure = _safe_float(
            (seed.get("event_exposure") if isinstance(seed, dict) else None)
            or exposure_matrix.get(sym, {}).get(event_type_lv2, 50.0),
            50.0,
        )
        event_relevance = _safe_float((seed.get("event_relevance") if isinstance(seed, dict) else None), 70.0)
        relative_strength = _safe_float((seed.get("relative_strength") if isinstance(seed, dict) else None), 70.0)
        liquidity_score = _safe_float((seed.get("liquidity_score") if isinstance(seed, dict) else None), s.get("liquidity_score", 0.7) * 100.0)
        risk_filter_score = _safe_float((seed.get("risk_filter_score") if isinstance(seed, dict) else None), 75.0)

        score_breakdown = {
            "event_exposure": round(0.35 * event_exposure, 2),
            "event_relevance": round(0.25 * event_relevance, 2),
            "relative_strength": round(0.20 * relative_strength, 2),
            "liquidity_score": round(0.10 * liquidity_score, 2),
            "risk_filter_score": round(0.10 * risk_filter_score, 2),
        }
        total = round(sum(score_breakdown.values()), 2)

        if event_exposure >= first_order_min:
            classification = "first_order_carrier"
        elif event_exposure >= leveraged_proxy_min:
            classification = "leveraged_proxy"
        else:
            classification = "contaminated"

        direction = str((seed.get("direction") if isinstance(seed, dict) else None) or "WATCH").upper()
        if direction not in {"LONG", "SHORT", "WATCH"}:
            direction = "WATCH"

        return {
            "symbol": sym,
            "name": str(s.get("name", sym)),
            "sector": str(s.get("sector", "")),
            "stock_transmission_score": total,
            "direction": direction,
            "classification": classification,
            "score_breakdown": score_breakdown,
        }

    # Prefer seeded candidates first.
    for cand in seeded:
        sym = str((cand or {}).get("symbol", "")).strip().upper()
        if not sym or sym in seen or sym not in premium:
            continue
        selected.append(_score(sym, cand))
        seen.add(sym)

    # Fill from primary sector if needed.
    if len(selected) < max_candidates and primary_sector:
        for sym, info in premium.items():
            if sym in seen:
                continue
            if str(info.get("sector", "")).strip() != primary_sector:
                continue
            selected.append(_score(sym, {"direction": "LONG"}))
            seen.add(sym)
            if len(selected) >= max_candidates:
                break

    selected.sort(key=lambda x: x.get("stock_transmission_score", 0.0), reverse=True)
    return selected[: max(0, int(max_candidates))]
