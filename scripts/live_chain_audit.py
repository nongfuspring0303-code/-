#!/usr/bin/env python3
"""
Minimal PR122 live chain audit summary.

This script intentionally stays small:
- read event/sector/opportunity records from JSON / JSONL
- summarize identity propagation coverage
- keep secondary sectors visible for audit
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "semantic_chain" / "sample_chain.jsonl"
DEFAULT_POLICY = ROOT / "configs" / "semantic_chain_policy.yaml"


def _load_policy(path: Path = DEFAULT_POLICY) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload if isinstance(payload, dict) else {}


def _load_records(path: Optional[str] = None) -> List[Dict[str, Any]]:
    source = Path(path) if path else DEFAULT_FIXTURE
    if not source.exists():
        return []
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
    except json.JSONDecodeError:
        pass

    records: List[Dict[str, Any]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        item = json.loads(raw)
        if isinstance(item, dict):
            records.append(item)
    return records


def _nonempty_count(records: Iterable[Dict[str, Any]], key: str) -> int:
    return sum(1 for record in records if str(record.get(key, "")).strip())


def _count_truthy(records: Iterable[Dict[str, Any]], key: str) -> int:
    total = 0
    for record in records:
        value = record.get(key)
        if isinstance(value, bool) and value:
            total += 1
        elif isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y", "not_called", "abstain", "parse_failed"}:
            total += 1
        elif value not in (None, "", 0, 0.0, False):
            total += 1
    return total


def _fallback_reason_distribution(records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        reason = str(record.get("fallback_reason", "")).strip()
        if not reason:
            provider_meta = record.get("provider_meta", {})
            if isinstance(provider_meta, dict):
                reason = str(provider_meta.get("fallback_reason", "")).strip()
        if reason:
            counts[reason] += 1
    return dict(counts)


def summarize_chain(records: Iterable[Dict[str, Any]], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rows = list(records)
    policy = policy or _load_policy()
    counts = Counter(str(row.get("type", "unknown")) for row in rows)
    event_hash_count = _nonempty_count(rows, "event_hash")
    semantic_trace_count = _nonempty_count(rows, "semantic_trace_id")
    missing_event_hash_count = sum(1 for row in rows if not str(row.get("event_hash", "")).strip())
    missing_semantic_trace_id_count = sum(1 for row in rows if not str(row.get("semantic_trace_id", "")).strip())
    opportunity_rows = [row for row in rows if str(row.get("type", "")).strip() == "opportunity_update"]
    sector_rows = [row for row in rows if str(row.get("type", "")).strip() == "sector_update"]
    primary_sector_count = sum(1 for row in sector_rows if str(row.get("primary_sector", "")).strip())
    secondary_sector_count = sum(
        1
        for row in sector_rows
        if any(str(sector.get("role", "")).strip().lower() == "secondary" for sector in row.get("sectors", []) if isinstance(sector, dict))
    )
    ticker_count = sum(
        1
        for row in opportunity_rows
        for opp in row.get("opportunities", [])
        if isinstance(opp, dict) and str(opp.get("symbol", "")).strip()
    )
    secondary_ticker_count = sum(
        1
        for row in opportunity_rows
        for opp in row.get("opportunities", [])
        if isinstance(opp, dict) and str(opp.get("sector_role", "")).strip().lower() == "secondary"
    )
    not_called_count = _count_truthy(rows, "not_called")
    abstain_count = _count_truthy(rows, "abstain")
    parse_failed_count = _count_truthy(rows, "parse_failed") + sum(1 for row in rows if str(row.get("parse_error_type", "")).strip())

    total = len(rows)
    return {
        "records_total": total,
        "type_counts": dict(counts),
        "missing_event_hash_count": missing_event_hash_count,
        "missing_semantic_trace_id_count": missing_semantic_trace_id_count,
        "event_hash_coverage": round(event_hash_count / total, 4) if total else 0.0,
        "semantic_trace_id_coverage": round(semantic_trace_count / total, 4) if total else 0.0,
        "fallback_reason_distribution": _fallback_reason_distribution(rows),
        "not_called_count": not_called_count,
        "abstain_count": abstain_count,
        "parse_failed_count": parse_failed_count,
        "primary_sector_count": primary_sector_count,
        "secondary_sector_count": secondary_sector_count,
        "ticker_count": ticker_count,
        "secondary_ticker_count": secondary_ticker_count,
        "threshold_status": str(policy.get("threshold_status", "proposed")),
        "enforcement_mode": str(policy.get("enforcement_mode", "observe_only")),
        "primary_sector_only": bool((policy.get("audit", {}) or {}).get("primary_sector_only", True)),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize live semantic chain audit coverage.")
    parser.add_argument("--input", help="JSON or JSONL file with chain records.", default="")
    args = parser.parse_args(argv)
    records = _load_records(args.input or None)
    summary = summarize_chain(records)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
