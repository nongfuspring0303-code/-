#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _p95(values: List[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    idx = max(0, min(len(sorted_values) - 1, int(round(0.95 * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_baseline(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("metrics", {})


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    return bool(value)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _output_gate_blockers(row: Dict[str, Any]) -> List[str]:
    output_gate = row.get("output_gate") if isinstance(row.get("output_gate"), dict) else {}
    blockers = output_gate.get("blockers") if isinstance(output_gate.get("blockers"), list) else []
    normalized = [str(x).strip().lower() for x in blockers if str(x).strip()]
    # Backward compatibility: some rows may store blocker codes at top-level.
    if not normalized:
        for key in ("a_gate_blocker_codes", "gate_blocker_codes"):
            vals = row.get(key)
            if isinstance(vals, list):
                normalized.extend(str(x).strip().lower() for x in vals if str(x).strip())
    return normalized


def _metric_missing_opportunity_but_execute(row: Dict[str, Any]) -> bool:
    if str(row.get("final_action", "")).upper() != "EXECUTE":
        return False

    has_opp_raw = row.get("has_opportunity")
    has_opp: bool | None = None if has_opp_raw is None else _as_bool(has_opp_raw)
    opp_count = _to_int(row.get("opportunity_count"))

    if has_opp is False:
        return True
    if opp_count is not None and opp_count <= 0:
        return True
    if has_opp is None and opp_count is None:
        # Compatibility-only fallback for legacy rows missing contract fields.
        reason = " ".join(
            str(row.get(k, "")) for k in ("final_reason", "reason", "reject_reason_text")
        ).lower()
        return "missing_opportunity" in reason
    return False


def _metric_market_data_default_used_in_execute(row: Dict[str, Any]) -> bool:
    if str(row.get("final_action", "")).upper() != "EXECUTE":
        return False

    default_used_raw = row.get("market_data_default_used")
    if default_used_raw is not None:
        return _as_bool(default_used_raw)

    blockers = _output_gate_blockers(row)
    if "market_data_default_used" in blockers:
        return True

    # Compatibility-only fallback for legacy rows missing contract fields.
    reason = " ".join(str(row.get(k, "")) for k in ("final_reason", "reason", "reject_reason_text")).lower()
    return "market_data_default_used" in reason


def compute_metrics(logs_dir: Path, baseline_path: Path) -> Dict[str, Any]:
    decision = _read_jsonl(logs_dir / "decision_gate.jsonl")
    replay_join = _read_jsonl(logs_dir / "replay_join_validation.jsonl")
    scorecard = _read_jsonl(logs_dir / "trace_scorecard.jsonl")
    raw_ingest = _read_jsonl(logs_dir / "raw_news_ingest.jsonl")

    execute_rows = [r for r in decision if str(r.get("final_action", "")).upper() == "EXECUTE"]
    missing_opp_execute = sum(1 for r in execute_rows if _metric_missing_opportunity_but_execute(r))
    default_execute = sum(1 for r in execute_rows if _metric_market_data_default_used_in_execute(r))

    non_whitelist_hits = sum(1 for r in scorecard if int(r.get("non_whitelist_sector_count", 0) or 0) > 0)
    placeholder_hits = sum(1 for r in scorecard if int(r.get("placeholder_count", 0) or 0) > 0)
    financial_hits = 0
    for row in scorecard:
        et = str(row.get("semantic_event_type", "")).lower()
        sectors = row.get("sector_candidates") or []
        if et == "financial" or any(str(s).strip() == "金融" for s in sectors):
            financial_hits += 1

    pk_complete = sum(1 for r in replay_join if bool(r.get("replay_primary_key_complete", False)))
    orphan_replay_total = sum(int(r.get("orphan_replay_count", 0) or 0) for r in replay_join)
    trace_join_ok = sum(
        1
        for r in replay_join
        if bool(r.get("replay_primary_key_complete", False))
        and int(r.get("orphan_replay_count", 0) or 0) == 0
        and int(r.get("orphan_execution_count", 0) or 0) == 0
    )

    decision_latency_samples: List[float] = []
    raw_first_by_trace: Dict[str, datetime] = {}
    for row in raw_ingest:
        trace_id = str(row.get("trace_id") or row.get("event_trace_id") or "").strip()
        ts = _parse_ts(row.get("logged_at"))
        if not trace_id or ts is None:
            continue
        if trace_id not in raw_first_by_trace or ts < raw_first_by_trace[trace_id]:
            raw_first_by_trace[trace_id] = ts

    for row in decision:
        ingest_ts = _parse_ts(row.get("ingest_ts"))
        decision_ts = _parse_ts(row.get("decision_ts") or row.get("logged_at"))
        if ingest_ts is None:
            trace_id = str(row.get("trace_id") or row.get("event_trace_id") or "").strip()
            ingest_ts = raw_first_by_trace.get(trace_id)
        if ingest_ts and decision_ts:
            delta = (decision_ts - ingest_ts).total_seconds()
            if delta >= 0:
                decision_latency_samples.append(delta)
    p95_latency = _p95(decision_latency_samples)

    trace_counts: Dict[str, int] = {}
    for row in raw_ingest:
        trace_id = str(row.get("trace_id") or row.get("event_trace_id") or "").strip()
        if not trace_id:
            continue
        trace_counts[trace_id] = trace_counts.get(trace_id, 0) + 1
    duplicate_trace_count = sum(1 for _, n in trace_counts.items() if n > 1)
    duplicate_rate = _safe_rate(duplicate_trace_count, len(trace_counts))

    baseline = _load_baseline(baseline_path)
    baseline_p95 = baseline.get("p95_decision_latency")
    baseline_duplicate_rate = baseline.get("same_trace_ai_duplicate_call_rate")

    sample_sizes = {
        "decision_gate_rows": len(decision),
        "scorecard_rows": len(scorecard),
        "replay_join_rows": len(replay_join),
        "raw_ingest_rows": len(raw_ingest),
    }
    insufficient_reasons = [f"{name}=0" for name, count in sample_sizes.items() if int(count) <= 0]
    insufficient_sample = len(insufficient_reasons) > 0

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "logs_dir": str(logs_dir),
        "sample_sizes": sample_sizes,
        "insufficient_sample": insufficient_sample,
        "insufficient_sample_reasons": insufficient_reasons,
        "metrics": {
            "missing_opportunity_but_execute_count": missing_opp_execute,
            "market_data_default_used_in_execute_count": default_execute,
            "sectors_non_whitelist_rate": _round(_safe_rate(non_whitelist_hits, len(scorecard))),
            "placeholder_leak_rate": _round(_safe_rate(placeholder_hits, len(scorecard))),
            "financial_rate": _round(_safe_rate(financial_hits, len(scorecard))),
            "replay_primary_key_completeness": _round(_safe_rate(pk_complete, len(replay_join))),
            "trace_join_success_rate": _round(_safe_rate(trace_join_ok, len(replay_join))),
            "orphan_replay": orphan_replay_total,
            "p95_decision_latency": _round(p95_latency),
            "same_trace_ai_duplicate_call_rate": _round(duplicate_rate),
        },
        "baseline_compare": {
            "p95_decision_latency_baseline": baseline_p95,
            "same_trace_ai_duplicate_call_rate_baseline": baseline_duplicate_rate,
            "p95_decision_latency_comparison": (
                "improved_or_equal"
                if baseline_p95 is not None and p95_latency is not None and p95_latency <= float(baseline_p95)
                else ("regressed" if baseline_p95 is not None and p95_latency is not None else "no_baseline")
            ),
            "same_trace_ai_duplicate_call_rate_comparison": (
                "improved_or_equal"
                if baseline_duplicate_rate is not None and duplicate_rate <= float(baseline_duplicate_rate)
                else ("regressed" if baseline_duplicate_rate is not None else "no_baseline")
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute Stage5 final acceptance metrics on clean-window logs")
    parser.add_argument("--logs-dir", type=Path, default=ROOT / "logs")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "artifacts" / "baseline" / "metrics_snapshot_2026-04-21.json",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = compute_metrics(logs_dir=args.logs_dir, baseline_path=args.baseline)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report.get("insufficient_sample") else 0


if __name__ == "__main__":
    raise SystemExit(main())
