#!/usr/bin/env python3
"""
Minimal strict report for PR122.

Reads the same chain records as live_chain_audit.py and surfaces identity
propagation plus primary-sector / secondary-sector audit behavior.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from live_chain_audit import _load_policy, _load_records, summarize_chain

ROOT = Path(__file__).resolve().parent.parent


def build_strict_report(records: List[Dict[str, Any]], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    policy = policy or _load_policy()
    summary = summarize_chain(records, policy=policy)
    opportunity_rows = [row for row in records if str(row.get("type", "")).strip() == "opportunity_update"]
    strict_join_ready = sum(
        1
        for row in opportunity_rows
        if str(row.get("event_hash", "")).strip() and str(row.get("semantic_trace_id", "")).strip()
    )
    secondary_ticker_count = sum(
        1
        for row in opportunity_rows
        for opp in row.get("opportunities", [])
        if isinstance(opp, dict) and str(opp.get("sector_role", "")).strip().lower() == "secondary"
    )
    report = {
        "summary": summary,
        "strict_join_ready_count": strict_join_ready,
        "strict_join_ready_rate": round(strict_join_ready / len(opportunity_rows), 4) if opportunity_rows else 0.0,
        "secondary_ticker_count": secondary_ticker_count,
        "fallback_pollution": secondary_ticker_count > 0,
        "comparison_status": "observe_only",
    }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a strict semantic mapping audit report.")
    parser.add_argument("--input", help="JSON or JSONL file with chain records.", default="")
    args = parser.parse_args(argv)
    records = _load_records(args.input or None)
    report = build_strict_report(records)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
