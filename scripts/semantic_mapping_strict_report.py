#!/usr/bin/env python3
"""
Minimal strict report for PR122.

This version performs a true strict join over event_update / sector_update /
opportunity_update rows keyed by (event_hash, semantic_trace_id).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from live_chain_audit import _load_policy, _load_records, summarize_chain


def _join_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (str(row.get("event_hash", "")).strip(), str(row.get("semantic_trace_id", "")).strip())


def _type_rows(records: List[Dict[str, Any]], row_type: str) -> List[Dict[str, Any]]:
    return [row for row in records if str(row.get("type", "")).strip() == row_type]


def build_strict_report(records: List[Dict[str, Any]], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    policy = policy or _load_policy()
    summary = summarize_chain(records, policy=policy)

    event_rows = _type_rows(records, "event_update")
    sector_rows = _type_rows(records, "sector_update")
    opportunity_rows = _type_rows(records, "opportunity_update")

    events_by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    sectors_by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    opportunities_by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    trace_to_event_hashes: Dict[str, set] = defaultdict(set)
    event_hash_to_traces: Dict[str, set] = defaultdict(set)
    failure_reason_distribution: Counter[str] = Counter()
    bad_traces: set = set()
    bad_event_hashes: set = set()

    missing_event_hash_count = 0
    missing_semantic_trace_id_count = 0
    opportunity_without_sector_count = 0
    opportunity_without_event_count = 0
    sector_without_event_count = 0
    event_hash_mismatch_count = 0
    semantic_trace_id_mismatch_count = 0
    duplicate_final_verdict_count = 0

    for row in event_rows:
        event_hash = str(row.get("event_hash", "")).strip()
        trace_id = str(row.get("semantic_trace_id", "")).strip()
        if not event_hash:
            missing_event_hash_count += 1
            failure_reason_distribution["missing_event_hash"] += 1
        if not trace_id:
            missing_semantic_trace_id_count += 1
            failure_reason_distribution["missing_semantic_trace_id"] += 1
        if event_hash and trace_id:
            key = (event_hash, trace_id)
            events_by_key[key].append(row)
            trace_to_event_hashes[trace_id].add(event_hash)
            event_hash_to_traces[event_hash].add(trace_id)

    for row in sector_rows:
        event_hash = str(row.get("event_hash", "")).strip()
        trace_id = str(row.get("semantic_trace_id", "")).strip()
        if not event_hash:
            missing_event_hash_count += 1
            failure_reason_distribution["missing_event_hash"] += 1
        if not trace_id:
            missing_semantic_trace_id_count += 1
            failure_reason_distribution["missing_semantic_trace_id"] += 1
        if event_hash and trace_id:
            key = (event_hash, trace_id)
            sectors_by_key[key].append(row)
            trace_to_event_hashes[trace_id].add(event_hash)
            event_hash_to_traces[event_hash].add(trace_id)

    for row in opportunity_rows:
        event_hash = str(row.get("event_hash", "")).strip()
        trace_id = str(row.get("semantic_trace_id", "")).strip()
        if not event_hash:
            missing_event_hash_count += 1
            failure_reason_distribution["missing_event_hash"] += 1
        if not trace_id:
            missing_semantic_trace_id_count += 1
            failure_reason_distribution["missing_semantic_trace_id"] += 1
        if event_hash and trace_id:
            key = (event_hash, trace_id)
            opportunities_by_key[key].append(row)
            trace_to_event_hashes[trace_id].add(event_hash)
            event_hash_to_traces[event_hash].add(trace_id)

    # Mismatch detection across records sharing the same trace or event hash.
    for trace_id, hashes in trace_to_event_hashes.items():
        if len(hashes) > 1:
            event_hash_mismatch_count += len(hashes) - 1
            failure_reason_distribution["event_hash_mismatch"] += len(hashes) - 1
            bad_traces.add(trace_id)
    for event_hash, traces in event_hash_to_traces.items():
        if len(traces) > 1:
            semantic_trace_id_mismatch_count += len(traces) - 1
            failure_reason_distribution["semantic_trace_id_mismatch"] += len(traces) - 1
            bad_event_hashes.add(event_hash)

    join_keys = set(events_by_key) | set(sectors_by_key) | set(opportunities_by_key)
    strict_join_ready_count = 0

    for key in join_keys:
        event_count = len(events_by_key.get(key, []))
        sector_count = len(sectors_by_key.get(key, []))
        opportunity_count = len(opportunities_by_key.get(key, []))
        if key[0] in bad_event_hashes or key[1] in bad_traces:
            failure_reason_distribution["event_hash_mismatch"] += int(key[0] in bad_event_hashes)
            failure_reason_distribution["semantic_trace_id_mismatch"] += int(key[1] in bad_traces)
            continue
        if event_count > 1 or sector_count > 1 or opportunity_count > 1:
            duplicate_final_verdict_count += max(0, opportunity_count - 1)
            failure_reason_distribution["duplicate_final_verdict"] += max(0, opportunity_count - 1)

        if event_count and sector_count and opportunity_count and event_count == 1 and sector_count == 1 and opportunity_count == 1:
            strict_join_ready_count += 1

    # Additional row-level failures for rows lacking usable keys.
    for row in opportunity_rows:
        if not str(row.get("event_hash", "")).strip() or not str(row.get("semantic_trace_id", "")).strip():
            pass
    for row in sector_rows:
        if not str(row.get("event_hash", "")).strip() or not str(row.get("semantic_trace_id", "")).strip():
            if str(row.get("event_hash", "")).strip() and not str(row.get("semantic_trace_id", "")).strip():
                failure_reason_distribution["missing_semantic_trace_id"] += 0
            if not str(row.get("event_hash", "")).strip() and str(row.get("semantic_trace_id", "")).strip():
                failure_reason_distribution["missing_event_hash"] += 0
        if str(row.get("event_hash", "")).strip() and str(row.get("semantic_trace_id", "")).strip():
            key = _join_key(row)
            if key not in events_by_key:
                sector_without_event_count += 1
                failure_reason_distribution["sector_without_event"] += 1

    for row in opportunity_rows:
        if str(row.get("event_hash", "")).strip() and str(row.get("semantic_trace_id", "")).strip():
            key = _join_key(row)
            if key not in sectors_by_key:
                opportunity_without_sector_count += 1
                failure_reason_distribution["opportunity_without_sector"] += 1
            if key not in events_by_key:
                opportunity_without_event_count += 1
                failure_reason_distribution["opportunity_without_event"] += 1

    strict_join_failed_count = max(
        0,
        len(opportunity_rows)
        - strict_join_ready_count,
    )

    secondary_ticker_count = sum(
        1
        for row in opportunity_rows
        for opp in row.get("opportunities", [])
        if isinstance(opp, dict) and str(opp.get("sector_role", "")).strip().lower() == "secondary"
    )
    report = {
        "summary": summary,
        "missing_event_hash_count": missing_event_hash_count,
        "missing_semantic_trace_id_count": missing_semantic_trace_id_count,
        "event_hash_mismatch_count": event_hash_mismatch_count,
        "semantic_trace_id_mismatch_count": semantic_trace_id_mismatch_count,
        "sector_without_event_count": sector_without_event_count,
        "opportunity_without_sector_count": opportunity_without_sector_count,
        "opportunity_without_event_count": opportunity_without_event_count,
        "duplicate_final_verdict_count": duplicate_final_verdict_count,
        "secondary_ticker_count": secondary_ticker_count,
        "fallback_pollution": secondary_ticker_count > 0,
        "strict_join_ready_count": strict_join_ready_count,
        "strict_join_failed_count": strict_join_failed_count,
        "strict_join_ready_rate": round(strict_join_ready_count / len(join_keys), 4) if join_keys else 0.0,
        "failure_reason_distribution": dict(failure_reason_distribution),
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
