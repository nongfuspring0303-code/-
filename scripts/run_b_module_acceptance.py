#!/usr/bin/env python3
"""
Phase-3 B-module acceptance harness.

Checks:
1) sector-switch latency P99 <= 1s
2) bullish->LONG, bearish->SHORT, differentiation >= 80%
3) premium-pool-only output
4) opportunity-card fields completeness
5) high-risk interception rate == 100% (BLOCK or PENDING_CONFIRM)
6) direction consistency >= 85% within same sector
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from statistics import quantiles
from typing import Any, Dict, List

from opportunity_score import OpportunityScorer


@dataclass
class AcceptanceResult:
    latency_p99_sec: float
    differentiation_rate: float
    bullish_long_ratio: float
    bearish_short_ratio: float
    premium_only_rate: float
    card_complete_rate: float
    high_risk_interception_rate: float
    direction_consistency_rate: float
    passed: bool


REQUIRED_CARD_FIELDS = {
    "symbol",
    "name",
    "sector",
    "signal",
    "entry_zone",
    "risk_flags",
    "final_action",
    "reasoning",
    "confidence",
    "timestamp",
}


def _latency_p99(latencies: List[float]) -> float:
    if not latencies:
        return 0.0
    if len(latencies) < 2:
        return latencies[0]
    # 100-quantiles => p99 at index 98
    q = quantiles(latencies, n=100)
    return float(q[98])


def _make_sector_payload(trace_id: str, sector: str, direction: str, impact: float, confidence: float) -> Dict[str, Any]:
    symbol_by_sector = {
        "科技": ["NVDA", "MSFT", "AAPL", "META"],
        "金融": ["JPM"],
        "能源": ["XOM"],
        "医疗": ["LLY"],
        "工业": ["CAT"],
    }
    candidates = [
        {
            "symbol": s,
            "sector": sector,
            "direction": direction,
            "event_beta": 1.2,
        }
        for s in symbol_by_sector.get(sector, [])
    ]
    return {
        "trace_id": trace_id,
        "schema_version": "v1.0",
        "sectors": [
            {
                "name": sector,
                "direction": direction,
                "impact_score": impact,
                "confidence": confidence,
            }
        ],
        "stock_candidates": candidates,
        "timestamp": "2026-04-04T00:00:00Z",
    }


def run_acceptance(round_name: str, seed: int, samples: int) -> Dict[str, Any]:
    random.seed(seed)
    scorer = OpportunityScorer()

    # 1) Sector-switch latency P99
    switch_sectors = ["科技", "金融", "能源", "医疗"]
    latencies = []
    for i in range(samples):
        sector = switch_sectors[i % len(switch_sectors)]
        direction = "LONG" if i % 2 == 0 else "SHORT"
        payload = _make_sector_payload(
            trace_id=f"{round_name}_lat_{i}",
            sector=sector,
            direction=direction,
            impact=0.7 + random.random() * 0.2,
            confidence=0.72 + random.random() * 0.2,
        )
        start = time.perf_counter()
        scorer.build_opportunity_update(payload)
        latencies.append(time.perf_counter() - start)
    latency_p99 = _latency_p99(latencies)

    # 2) Differentiation (bullish/bearish)
    bull_total = 0
    bull_long = 0
    bear_total = 0
    bear_short = 0
    for i in range(samples):
        bull = _make_sector_payload(f"{round_name}_bull_{i}", "科技", "LONG", 0.8, 0.85)
        bear = _make_sector_payload(f"{round_name}_bear_{i}", "科技", "SHORT", 0.8, 0.85)

        bull_out = scorer.build_opportunity_update(bull)
        bear_out = scorer.build_opportunity_update(bear)

        for opp in bull_out.get("opportunities", []):
            bull_total += 1
            if opp.get("signal") == "LONG":
                bull_long += 1

        for opp in bear_out.get("opportunities", []):
            bear_total += 1
            if opp.get("signal") == "SHORT":
                bear_short += 1

    bullish_long_ratio = (bull_long / bull_total) if bull_total else 0.0
    bearish_short_ratio = (bear_short / bear_total) if bear_total else 0.0
    differentiation_rate = (bullish_long_ratio + bearish_short_ratio) / 2

    # 3) Premium-only + 4) Card completeness
    premium_total = 0
    premium_ok = 0
    card_total = 0
    card_ok = 0

    mixed_payload = {
        "trace_id": f"{round_name}_mixed",
        "schema_version": "v1.0",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.84, "confidence": 0.9},
            {"name": "工业", "direction": "SHORT", "impact_score": 0.76, "confidence": 0.83},
        ],
        "stock_candidates": [
            {"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.3},
            {"symbol": "MSFT", "sector": "科技", "direction": "LONG", "event_beta": 1.1},
            {"symbol": "CAT", "sector": "工业", "direction": "SHORT", "event_beta": 1.2},
            {"symbol": "UNKNOWN", "sector": "工业", "direction": "SHORT", "event_beta": 1.2},
        ],
    }
    mixed_out = scorer.build_opportunity_update(mixed_payload)

    for opp in mixed_out.get("opportunities", []):
        premium_total += 1
        if scorer.pool.get_stock(opp.get("symbol", "")) is not None and scorer.pool._pass_thresholds(  # noqa: SLF001
            scorer.pool.get_stock(opp.get("symbol", ""))
        ):
            premium_ok += 1

        card_total += 1
        keys_ok = REQUIRED_CARD_FIELDS.issubset(opp.keys())
        zone = opp.get("entry_zone", {})
        zone_ok = isinstance(zone, dict) and {"support", "resistance"}.issubset(zone.keys())
        reason_ok = isinstance(opp.get("reasoning", ""), str) and len(opp.get("reasoning", "")) > 0
        if keys_ok and zone_ok and reason_ok:
            card_ok += 1

    premium_only_rate = (premium_ok / premium_total) if premium_total else 1.0
    card_complete_rate = (card_ok / card_total) if card_total else 1.0

    # 5) High-risk interception rate
    high_risk_total = 0
    high_risk_intercepted = 0
    for i in range(samples):
        # Force low confidence + direction conflict => high risk guaranteed
        payload = {
            "trace_id": f"{round_name}_risk_{i}",
            "schema_version": "v1.0",
            "sectors": [
                {"name": "金融", "direction": "LONG", "impact_score": 0.58, "confidence": 0.45}
            ],
            "stock_candidates": [
                {"symbol": "JPM", "sector": "金融", "direction": "SHORT", "event_beta": 1.0}
            ],
        }
        out = scorer.build_opportunity_update(payload)
        for opp in out.get("opportunities", []):
            flags = opp.get("risk_flags", [])
            is_high_risk = any(f.get("level") == "high" for f in flags)
            if is_high_risk:
                high_risk_total += 1
                if opp.get("final_action") in ("BLOCK", "PENDING_CONFIRM"):
                    high_risk_intercepted += 1

    high_risk_interception_rate = (high_risk_intercepted / high_risk_total) if high_risk_total else 1.0

    # 6) Direction consistency in same sector
    consistency_total = 0
    consistency_match = 0
    for i in range(samples):
        direction = "LONG" if i % 2 == 0 else "SHORT"
        payload = _make_sector_payload(
            trace_id=f"{round_name}_cons_{i}",
            sector="科技",
            direction=direction,
            impact=0.82,
            confidence=0.87,
        )
        out = scorer.build_opportunity_update(payload)
        opps = out.get("opportunities", [])
        if not opps:
            continue
        consistency_total += len(opps)
        consistency_match += sum(1 for x in opps if x.get("signal") == direction)

    direction_consistency_rate = (consistency_match / consistency_total) if consistency_total else 0.0

    res = AcceptanceResult(
        latency_p99_sec=latency_p99,
        differentiation_rate=differentiation_rate,
        bullish_long_ratio=bullish_long_ratio,
        bearish_short_ratio=bearish_short_ratio,
        premium_only_rate=premium_only_rate,
        card_complete_rate=card_complete_rate,
        high_risk_interception_rate=high_risk_interception_rate,
        direction_consistency_rate=direction_consistency_rate,
        passed=(
            latency_p99 <= 1.0
            and differentiation_rate >= 0.80
            and premium_only_rate >= 1.0
            and card_complete_rate >= 1.0
            and high_risk_interception_rate >= 1.0
            and direction_consistency_rate >= 0.85
        ),
    )

    return {
        "round": round_name,
        "seed": seed,
        "samples": samples,
        "metrics": {
            "latency_p99_sec": round(res.latency_p99_sec, 6),
            "differentiation_rate": round(res.differentiation_rate, 4),
            "bullish_long_ratio": round(res.bullish_long_ratio, 4),
            "bearish_short_ratio": round(res.bearish_short_ratio, 4),
            "premium_only_rate": round(res.premium_only_rate, 4),
            "card_complete_rate": round(res.card_complete_rate, 4),
            "high_risk_interception_rate": round(res.high_risk_interception_rate, 4),
            "direction_consistency_rate": round(res.direction_consistency_rate, 4),
        },
        "thresholds": {
            "latency_p99_sec": "<=1.0",
            "differentiation_rate": ">=0.80",
            "premium_only_rate": "==1.0",
            "card_complete_rate": "==1.0",
            "high_risk_interception_rate": "==1.0",
            "direction_consistency_rate": ">=0.85",
        },
        "passed": res.passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run B-module acceptance checks")
    parser.add_argument("--round", type=str, required=True, help="Round name, e.g. round1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples", type=int, default=1000)
    args = parser.parse_args()

    out = run_acceptance(args.round, args.seed, args.samples)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
