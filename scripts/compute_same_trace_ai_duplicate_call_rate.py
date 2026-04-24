#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _load_baseline_rate(path: Path) -> float | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("metrics", {})
    value = metrics.get("same_trace_ai_duplicate_call_rate")
    if value is None:
        return None
    return float(value)


def compute_duplicate_rate(logs_dir: Path, baseline_path: Path) -> Dict[str, Any]:
    raw_rows = _read_jsonl(logs_dir / "raw_news_ingest.jsonl")
    counts: Counter[str] = Counter()
    for row in raw_rows:
        trace_id = str(row.get("trace_id") or row.get("event_trace_id") or "").strip()
        if trace_id:
            counts[trace_id] += 1

    total_traces = len(counts)
    duplicate_traces = sum(1 for _, n in counts.items() if n > 1)
    insufficient_sample = total_traces == 0
    duplicate_rate = None if insufficient_sample else round(_safe_rate(duplicate_traces, total_traces), 6)
    baseline_rate = _load_baseline_rate(baseline_path)

    comparison = "insufficient_sample" if insufficient_sample else "no_baseline"
    if not insufficient_sample and baseline_rate is not None:
        comparison = "improved_or_equal" if duplicate_rate <= baseline_rate else "regressed"

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "logs_dir": str(logs_dir),
        "metric": "same_trace_ai_duplicate_call_rate",
        "total_traces": total_traces,
        "duplicate_traces": duplicate_traces,
        "current_value": duplicate_rate,
        "insufficient_sample": insufficient_sample,
        "baseline_path": str(baseline_path),
        "baseline_value": baseline_rate,
        "comparison": comparison,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute same_trace_ai_duplicate_call_rate from clean-window logs")
    parser.add_argument("--logs-dir", type=Path, default=ROOT / "logs")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "artifacts" / "baseline" / "metrics_snapshot_2026-04-21.json",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = compute_duplicate_rate(logs_dir=args.logs_dir, baseline_path=args.baseline)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report.get("insufficient_sample") else 0


if __name__ == "__main__":
    raise SystemExit(main())
