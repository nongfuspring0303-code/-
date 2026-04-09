#!/usr/bin/env python3
"""Verify mapping family coverage and precision on canonical samples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


CASES = [
    ("A", "bank run sparks liquidity crisis fears", "credit crunch", "template:liquidity_stress_chain"),
    ("B", "public health emergency after pandemic surge", "lockdown", "template:public_health_chain"),
    ("D", "geopolitical conflict escalates after missile strike", "war escalation", "template:geo_risk_chain"),
    ("F", "nonfarm payroll and cpi miss expectations", "macro data shock", "template:macro_data_chain"),
    ("G", "market structure reform changes circuit breaker rules", "trading regulation", "template:market_structure_chain"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify mapping quality")
    parser.add_argument("--min-family-coverage", type=float, default=1.0)
    parser.add_argument("--min-precision", type=float, default=0.9)
    args = parser.parse_args()

    mapper = ConductionMapper()
    total = len(CASES)
    correct = 0
    covered = set()
    details = []

    for category, headline, summary, expected in CASES:
        out = mapper.run(
            {
                "event_id": f"ME-{category}-VERIFY-001",
                "category": category,
                "severity": "E2",
                "headline": headline,
                "summary": summary,
                "lifecycle_state": "Active",
                "sector_data": [{"sector": "Technology", "industry": "Technology"}],
            }
        )
        got = out.data.get("mapping_source") if out.status.value == "success" else ""
        ok = got == expected
        if ok:
            correct += 1
            covered.add(category)
        details.append({"category": category, "expected": expected, "got": got, "ok": ok})

    expected_families = len({case[0] for case in CASES})
    family_coverage = len(covered) / max(expected_families, 1)
    precision = correct / max(total, 1)
    passed = family_coverage >= args.min_family_coverage and precision >= args.min_precision

    print(
        json.dumps(
            {
                "family_coverage": round(family_coverage, 4),
                "precision": round(precision, 4),
                "min_family_coverage": args.min_family_coverage,
                "min_precision": args.min_precision,
                "passed": passed,
                "details": details,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
