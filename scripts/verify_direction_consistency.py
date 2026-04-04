#!/usr/bin/env python3
"""
B-2 verification script.

Validate long/short differentiation rate based on synthetic bullish/bearish
sector updates and premium stock pool constraints.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from opportunity_score import OpportunityScorer, evaluate_direction_consistency


def _build_case(trace_id: str, direction: str, impact: float, confidence: float, symbol: str = "NVDA") -> Dict[str, Any]:
    return {
        "trace_id": trace_id,
        "schema_version": "v1.0",
        "sectors": [
            {
                "name": "科技",
                "direction": direction,
                "impact_score": impact,
                "confidence": confidence,
            }
        ],
        "stock_candidates": [
            {
                "symbol": symbol,
                "sector": "科技",
                "direction": direction,
                "event_beta": 1.2,
            }
        ],
        "timestamp": "2026-04-04T00:00:00Z",
    }


def _generate_cases(count: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    bullish: List[Dict[str, Any]] = []
    bearish: List[Dict[str, Any]] = []

    for i in range(count):
        # Add slight deterministic oscillation to avoid all-identical cases.
        wobble = (i % 5) * 0.01
        bullish.append(
            _build_case(
                trace_id=f"bull_{i:03d}",
                direction="LONG",
                impact=0.72 + wobble,
                confidence=0.80 - wobble,
                symbol="NVDA",
            )
        )
        bearish.append(
            _build_case(
                trace_id=f"bear_{i:03d}",
                direction="SHORT",
                impact=0.71 + wobble,
                confidence=0.79 - wobble,
                symbol="NVDA",
            )
        )

    return bullish, bearish


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify LONG/SHORT differentiation consistency")
    parser.add_argument("--samples", type=int, default=100, help="Number of bullish and bearish samples")
    parser.add_argument("--min-rate", type=float, default=0.80, help="Minimum differentiation rate")
    parser.add_argument("--pool-config", type=str, default=None, help="Override premium stock pool config path")
    args = parser.parse_args()

    scorer = OpportunityScorer(pool_config_path=args.pool_config)
    bullish_cases, bearish_cases = _generate_cases(args.samples)
    metrics = evaluate_direction_consistency(scorer, bullish_cases, bearish_cases)

    passed = metrics["differentiation_rate"] >= args.min_rate
    report = {
        "samples_per_side": args.samples,
        "min_rate": args.min_rate,
        **metrics,
        "passed": passed,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
