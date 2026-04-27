#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_PIPELINE_STAGES = {
    "intel_ingest",
    "lifecycle",
    "fatigue",
    "conduction",
    "market_validation",
    "semantic",
    "path_adjudication",
    "signal",
    "opportunity",
    "execution",
}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _hour_bucket(record: Dict[str, Any]) -> str:
    ts = _parse_ts(str(record.get("logged_at")))
    return ts.strftime("%Y-%m-%dT%H:00:00Z")


def _day_bucket(record: Dict[str, Any]) -> str:
    ts = _parse_ts(str(record.get("logged_at")))
    return ts.strftime("%Y-%m-%d")


def _hourly_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("logged_at"):
            out[_hour_bucket(row)] += 1
    return out


def build_provider_health_hourly(market_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in market_records:
        if row.get("logged_at"):
            grouped[_hour_bucket(row)].append(row)

    out: List[Dict[str, Any]] = []
    for hour in sorted(grouped.keys()):
        rows = grouped[hour]
        total = len(rows)
        present_count = sum(1 for r in rows if bool(r.get("market_data_present", False)))
        stale_count = sum(1 for r in rows if bool(r.get("market_data_stale", False)))
        default_count = sum(1 for r in rows if bool(r.get("market_data_default_used", False)))
        market_fallback_count = sum(1 for r in rows if bool(r.get("market_data_fallback_used", False)))
        provider_fallback_count = sum(1 for r in rows if bool(r.get("fallback_used", False)))
        source_count: Dict[str, int] = defaultdict(int)
        provider_failed_count = 0
        unresolved_symbol_count = 0
        fallback_reason_counts: Dict[str, int] = defaultdict(int)
        provider_failure_reason_counts: Dict[str, int] = defaultdict(int)
        for row in rows:
            source = str(row.get("market_data_source", "unknown"))
            source_count[source] += 1
            providers_failed = row.get("providers_failed", [])
            if isinstance(providers_failed, list):
                provider_failed_count += len([x for x in providers_failed if str(x).strip()])
            unresolved_raw = row.get("unresolved_symbols", [])
            if isinstance(unresolved_raw, list):
                unresolved_symbol_count += len([x for x in unresolved_raw if str(x).strip()])
            reason = str(row.get("fallback_reason", "") or "").strip()
            if reason:
                fallback_reason_counts[reason] += 1
            failure_reasons_raw = row.get("provider_failure_reasons", {})
            if isinstance(failure_reasons_raw, dict):
                for provider, reason_value in failure_reasons_raw.items():
                    provider_name = str(provider or "").strip()
                    reason_name = str(reason_value or "").strip()
                    if provider_name and reason_name:
                        provider_failure_reason_counts[f"{provider_name}:{reason_name}"] += 1

        present_rate = present_count / total if total else 0.0
        stale_rate = stale_count / total if total else 0.0
        default_rate = default_count / total if total else 0.0
        market_fallback_rate = market_fallback_count / total if total else 0.0
        provider_fallback_rate = provider_fallback_count / total if total else 0.0

        status = "healthy"
        if stale_rate > 0.20 or default_rate > 0.10:
            status = "degraded"
        if present_rate < 0.80 or default_rate > 0.30:
            status = "critical"

        out.append(
            {
                "hour_bucket_utc": hour,
                "total_records": total,
                "present_rate": round(present_rate, 4),
                "stale_rate": round(stale_rate, 4),
                "default_used_rate": round(default_rate, 4),
                # Backward-compatible alias: fallback_used_rate keeps market-level fallback semantics.
                "fallback_used_rate": round(market_fallback_rate, 4),
                "market_fallback_used_count": market_fallback_count,
                "market_fallback_used_rate": round(market_fallback_rate, 4),
                "provider_fallback_used_count": provider_fallback_count,
                "provider_fallback_used_rate": round(provider_fallback_rate, 4),
                "provider_sources": dict(sorted(source_count.items())),
                "provider_failed_count": provider_failed_count,
                "unresolved_symbol_count": unresolved_symbol_count,
                "fallback_reason_counts": dict(sorted(fallback_reason_counts.items())),
                "provider_failure_reason_counts": dict(sorted(provider_failure_reason_counts.items())),
                "health_status": status,
            }
        )
    return out


def _trace_stage_coverage_rate(pipeline_rows: List[Dict[str, Any]]) -> float:
    if not pipeline_rows:
        return 0.0
    stages_by_trace: Dict[str, set[str]] = defaultdict(set)
    for row in pipeline_rows:
        trace_id = str(row.get("trace_id", ""))
        stage = str(row.get("stage", ""))
        if trace_id and stage:
            stages_by_trace[trace_id].add(stage)

    if not stages_by_trace:
        return 0.0
    covered = sum(1 for stages in stages_by_trace.values() if REQUIRED_PIPELINE_STAGES.issubset(stages))
    return covered / len(stages_by_trace)


def build_system_health_daily(
    *,
    raw_ingest_rows: List[Dict[str, Any]],
    pipeline_rows: List[Dict[str, Any]],
    decision_rows: List[Dict[str, Any]],
    rejected_rows: List[Dict[str, Any]],
    quarantine_rows: List[Dict[str, Any]],
    trace_scorecard_rows: List[Dict[str, Any]],
    gate_enabled: bool,
) -> List[Dict[str, Any]]:
    grouped_days: set[str] = set()
    for rows in (raw_ingest_rows, pipeline_rows, decision_rows, rejected_rows, quarantine_rows, trace_scorecard_rows):
        for row in rows:
            if row.get("logged_at"):
                grouped_days.add(_day_bucket(row))

    out: List[Dict[str, Any]] = []
    for day in sorted(grouped_days):
        day_raw = [r for r in raw_ingest_rows if r.get("logged_at", "").startswith(day)]
        day_pipeline = [r for r in pipeline_rows if r.get("logged_at", "").startswith(day)]
        day_decision = [r for r in decision_rows if r.get("logged_at", "").startswith(day)]
        day_rejected = [r for r in rejected_rows if r.get("logged_at", "").startswith(day)]
        day_quarantine = [r for r in quarantine_rows if r.get("logged_at", "").startswith(day)]
        day_score = [r for r in trace_scorecard_rows if r.get("logged_at", "").startswith(day)]
        day_rejected_hourly = _hourly_counts(day_rejected)
        day_quarantine_hourly = _hourly_counts(day_quarantine)
        day_ingest_hourly = _hourly_counts(day_raw)

        ingest_count = len(day_raw)
        rejected_count = len(day_rejected)
        quarantine_count = len(day_quarantine)
        decision_count = len(day_decision)
        execute_count = sum(1 for row in day_decision if str(row.get("final_action", "")).upper() == "EXECUTE")
        stage_coverage_rate = _trace_stage_coverage_rate(day_pipeline)
        avg_trace_score = (
            sum(float((row.get("scores") or {}).get("total_score", 0.0)) for row in day_score) / len(day_score)
            if day_score
            else 0.0
        )
        alert_hours = []
        if gate_enabled:
            for hour_bucket, ingest_hour_count in sorted(day_ingest_hourly.items()):
                if ingest_hour_count > 0 and day_rejected_hourly.get(hour_bucket, 0) == 0 and day_quarantine_hourly.get(hour_bucket, 0) == 0:
                    alert_hours.append(hour_bucket)
        quarantine_silent_alert = bool(alert_hours)

        status = "healthy"
        if stage_coverage_rate < 1.0 or avg_trace_score < 70:
            status = "degraded"
        if quarantine_silent_alert or ingest_count > 0 and decision_count == 0:
            status = "critical"

        out.append(
            {
                "date_utc": day,
                "ingest_count": ingest_count,
                "pipeline_stage_count": len(day_pipeline),
                "decision_gate_count": decision_count,
                "execute_count": execute_count,
                "rejected_events_count": rejected_count,
                "quarantine_replay_count": quarantine_count,
                "trace_stage_coverage_rate": round(stage_coverage_rate, 4),
                "avg_trace_score": round(avg_trace_score, 2),
                "quarantine_activity_monitor": {
                    "gate_enabled": gate_enabled,
                    "hours_checked": len(day_ingest_hourly),
                    "alert_hours_utc": alert_hours,
                    "alert": "QUARANTINE_SILENT_ALERT" if quarantine_silent_alert else "",
                },
                "health_status": status,
            }
        )
    return out


def build_daily_report_md(
    *,
    provider_health: List[Dict[str, Any]],
    system_health: List[Dict[str, Any]],
) -> str:
    lines = [
        "# Stage5 Daily Health Report",
        "",
        f"- generated_at_utc: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        "",
        "## System Health Daily",
    ]
    if not system_health:
        lines.append("- no system-health records")
    else:
        for row in system_health:
            lines.append(
                f"- {row['date_utc']}: status={row['health_status']}, ingest={row['ingest_count']}, "
                f"rejected={row['rejected_events_count']}, quarantine={row['quarantine_replay_count']}, "
                f"coverage={row['trace_stage_coverage_rate']:.2f}, avg_trace_score={row['avg_trace_score']:.2f}"
            )

    lines.append("")
    lines.append("## Provider Health Hourly")
    if not provider_health:
        lines.append("- no provider-health records")
    else:
        for row in provider_health:
            lines.append(
                f"- {row['hour_bucket_utc']}: status={row['health_status']}, present_rate={row['present_rate']:.2f}, "
                f"stale_rate={row['stale_rate']:.2f}, default_rate={row['default_used_rate']:.2f}, "
                f"market_fallback_rate={row['market_fallback_used_rate']:.2f}, "
                f"provider_fallback_rate={row['provider_fallback_used_rate']:.2f}"
            )
    lines.append("")
    return "\n".join(lines)


def evaluate_logs(logs_dir: Path, gate_enabled: bool = True) -> Dict[str, Any]:
    raw_ingest = _read_jsonl(logs_dir / "raw_news_ingest.jsonl")
    market = _read_jsonl(logs_dir / "market_data_provenance.jsonl")
    pipeline = _read_jsonl(logs_dir / "pipeline_stage.jsonl")
    decision = _read_jsonl(logs_dir / "decision_gate.jsonl")
    rejected = _read_jsonl(logs_dir / "rejected_events.jsonl")
    quarantine = _read_jsonl(logs_dir / "quarantine_replay.jsonl")
    trace_scorecard = _read_jsonl(logs_dir / "trace_scorecard.jsonl")

    provider_health = build_provider_health_hourly(market)
    system_health = build_system_health_daily(
        raw_ingest_rows=raw_ingest,
        pipeline_rows=pipeline,
        decision_rows=decision,
        rejected_rows=rejected,
        quarantine_rows=quarantine,
        trace_scorecard_rows=trace_scorecard,
        gate_enabled=gate_enabled,
    )
    report_md = build_daily_report_md(provider_health=provider_health, system_health=system_health)

    return {
        "provider_health_hourly": provider_health,
        "system_health_daily": system_health,
        "daily_report_markdown": report_md,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Stage5 logs and generate provider/system health snapshots.")
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument(
        "--gate-enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable gate-aware quarantine-silent alert evaluation.",
    )
    parser.add_argument("--provider-out", type=Path, default=None)
    parser.add_argument("--system-out", type=Path, default=None)
    parser.add_argument("--report-out", type=Path, default=None)
    args = parser.parse_args()

    logs_dir = args.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    provider_out = args.provider_out or (logs_dir / "provider_health_hourly.json")
    system_out = args.system_out or (logs_dir / "system_health_daily.json")
    report_out = args.report_out or (logs_dir / "system_health_daily_report.md")

    evaluated = evaluate_logs(logs_dir=logs_dir, gate_enabled=bool(args.gate_enabled))

    provider_out.write_text(json.dumps(evaluated["provider_health_hourly"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    system_out.write_text(json.dumps(evaluated["system_health_daily"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_out.write_text(str(evaluated["daily_report_markdown"]), encoding="utf-8")

    print(
        json.dumps(
            {
                "logs_dir": str(logs_dir),
                "provider_health_hourly_out": str(provider_out),
                "system_health_daily_out": str(system_out),
                "daily_report_out": str(report_out),
                "provider_health_hours": len(evaluated["provider_health_hourly"]),
                "system_health_days": len(evaluated["system_health_daily"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
