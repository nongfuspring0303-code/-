#!/usr/bin/env python3
"""Compute and freeze stage-0 baseline snapshots from local logs.

This script updates:
- artifacts/baseline/metrics_snapshot_2026-04-21.json
- artifacts/baseline/stress_metrics_snapshot_2026-04-21.json
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LOCAL_TZ = timezone(timedelta(hours=8))
BUS_LOG = ROOT / "logs" / "event_bus_live.jsonl"
REPLAY_LOG = ROOT / "logs" / "action_card_replay.jsonl"
SNAPSHOT_BASELINE = ROOT / "artifacts" / "baseline" / "metrics_snapshot_2026-04-21.json"
SNAPSHOT_STRESS = ROOT / "artifacts" / "baseline" / "stress_metrics_snapshot_2026-04-21.json"
SECTOR_MAPPING = ROOT / "configs" / "sector_impact_mapping.yaml"
PREMIUM_POOL = ROOT / "configs" / "premium_stock_pool.yaml"


@dataclass
class Context:
    bus: list[dict[str, Any]]
    replay: list[dict[str, Any]]


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    idx = max(0, min(len(sorted_values) - 1, int(round(0.95 * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def _safe_rate(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator > 0 else 0.0


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _sector_whitelist() -> set[str]:
    whitelist: set[str] = {
        "金融",
        "科技",
        "能源",
        "工业",
        "医疗",
        "消费",
        "公用事业",
        "房地产",
        "材料",
        "通信服务",
        "半导体",
        "航空",
        "成长股",
    }

    if PREMIUM_POOL.exists():
        with PREMIUM_POOL.open("r", encoding="utf-8") as f:
            pool = yaml.safe_load(f) or {}
        for row in pool.get("stocks", []):
            sector = str((row or {}).get("sector", "")).strip()
            if sector:
                whitelist.add(sector)

    if SECTOR_MAPPING.exists():
        with SECTOR_MAPPING.open("r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f) or {}
        for row in mapping.get("mappings", []):
            sector = str((row or {}).get("sector", "")).strip()
            if sector:
                whitelist.add(sector)

    return whitelist


def _collect_context() -> Context:
    return Context(
        bus=_load_jsonl(BUS_LOG),
        replay=_load_jsonl(REPLAY_LOG),
    )


def _compute_metrics(ctx: Context) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    trace_types: dict[str, set[str]] = defaultdict(set)
    trace_first_news_ts: dict[str, datetime] = {}
    trace_first_event_ts: dict[str, datetime] = {}
    event_count_by_trace: Counter[str] = Counter()

    with_ai = 0
    fallback = 0
    provider_timeout = 0
    provider_rate_limited = 0

    sector_names: list[str] = []

    for row in ctx.bus:
        trace_id = str(row.get("trace_id", "")).strip()
        msg_type = str(row.get("type", "")).strip()
        if trace_id and msg_type:
            trace_types[trace_id].add(msg_type)

        if msg_type == "sector_update":
            payload = row.get("payload") or {}
            for sector in payload.get("sectors", []) or []:
                name = str((sector or {}).get("name", "")).strip()
                if name:
                    sector_names.append(name)

        if msg_type != "event_update":
            continue

        if trace_id:
            event_count_by_trace[trace_id] += 1

        payload = row.get("payload") or {}
        ai_verdict = str(payload.get("ai_verdict", "")).strip().lower()
        ai_reason = str(payload.get("ai_reason", "")).strip().lower()

        if ai_verdict or ai_reason:
            with_ai += 1
        if ai_reason:
            fallback += 1
        if "timeout" in ai_reason:
            provider_timeout += 1
        if "429" in ai_reason or "rate_limit" in ai_reason or "too many requests" in ai_reason:
            provider_rate_limited += 1

        news_ts = _parse_time(payload.get("news_timestamp"))
        if trace_id and news_ts and (trace_id not in trace_first_news_ts or news_ts < trace_first_news_ts[trace_id]):
            trace_first_news_ts[trace_id] = news_ts

        bus_ts = _parse_time(row.get("timestamp"))
        if trace_id and bus_ts and (trace_id not in trace_first_event_ts or bus_ts < trace_first_event_ts[trace_id]):
            trace_first_event_ts[trace_id] = bus_ts

    traces_with_event = sum(1 for types in trace_types.values() if "event_update" in types)
    traces_with_all = sum(
        1
        for types in trace_types.values()
        if {"event_update", "sector_update", "opportunity_update"}.issubset(types)
    )
    traces_without_sector = sum(
        1 for types in trace_types.values() if "event_update" in types and "sector_update" not in types
    )

    whitelist = _sector_whitelist()
    non_whitelist_count = sum(1 for name in sector_names if name not in whitelist)
    financial_count = sum(1 for name in sector_names if name == "金融")

    exec_replay = [row for row in ctx.replay if str(row.get("final_action", "")).upper() == "EXECUTE"]
    missing_opp_exec = sum(
        1
        for row in exec_replay
        if "opportunity_update" not in trace_types.get(str(row.get("trace_id", "")).strip(), set())
    )

    replay_key_ok = sum(1 for row in ctx.replay if row.get("trace_id") and row.get("logged_at"))
    blocked_by_gate = 0
    market_data_default_used = 0
    decision_latency_samples: list[float] = []
    for row in ctx.replay:
        blockers = ((row.get("action_card") or {}).get("blockers") or [])
        if any(str(item).startswith("execution_gate_") for item in blockers):
            blocked_by_gate += 1
        if any("market_data_default_used" in str(item) for item in blockers):
            market_data_default_used += 1

        event_time = _parse_time((row.get("action_card") or {}).get("event_time"))
        logged_at = _parse_time(row.get("logged_at"))
        if event_time and logged_at:
            delta = (logged_at - event_time).total_seconds()
            if delta >= 0:
                decision_latency_samples.append(delta)

    raw_to_event_samples: list[float] = []
    for trace_id, news_ts in trace_first_news_ts.items():
        event_ts = trace_first_event_ts.get(trace_id)
        if not event_ts:
            continue
        delta = (event_ts - news_ts).total_seconds()
        if delta >= 0:
            raw_to_event_samples.append(delta)

    duplicate_trace_count = sum(1 for _, count in event_count_by_trace.items() if count > 1)
    duplicate_rate = _safe_rate(duplicate_trace_count, len(event_count_by_trace))

    baseline = {
        "missing_opportunity_but_execute_rate": _round(_safe_rate(missing_opp_exec, len(exec_replay))),
        "fallback_leak_rate": _round(_safe_rate(fallback, with_ai)),
        "financial_rate": _round(_safe_rate(financial_count, len(sector_names))),
        "sectors_non_whitelist_rate": _round(_safe_rate(non_whitelist_count, len(sector_names))),
        "replay_primary_key_completeness": _round(_safe_rate(replay_key_ok, len(ctx.replay))),
        "trace_join_success_rate": _round(_safe_rate(traces_with_all, traces_with_event)),
        "event_without_sector_rate": _round(_safe_rate(traces_without_sector, traces_with_event)),
        "p95_decision_latency": _round(_p95(decision_latency_samples)),
        "same_trace_ai_duplicate_call_rate": _round(duplicate_rate),
    }

    stress = {
        "queue_backlog_peak": _round(max(raw_to_event_samples) if raw_to_event_samples else None),
        "raw_ingest_to_event_update_p95": _round(_p95(raw_to_event_samples)),
        "raw_ingest_to_replay_p95": _round(_p95(decision_latency_samples)),
        "provider_timeout_rate": _round(_safe_rate(provider_timeout, with_ai)),
        "provider_rate_limited_rate": _round(_safe_rate(provider_rate_limited, with_ai)),
        "same_trace_ai_duplicate_call_rate": _round(duplicate_rate),
        "market_data_default_used_rate": _round(_safe_rate(market_data_default_used, len(ctx.replay))),
        "execution_blocked_by_gate_rate": _round(_safe_rate(blocked_by_gate, len(ctx.replay))),
    }

    debug = {
        "event_bus_rows": len(ctx.bus),
        "replay_rows": len(ctx.replay),
        "traces_with_event": traces_with_event,
        "traces_with_all_updates": traces_with_all,
        "trace_sector_absent": traces_without_sector,
        "sector_update_rows": len(sector_names),
        "sector_distribution": Counter(sector_names),
        "with_ai_rows": with_ai,
    }
    return baseline, stress, debug


def _git_sha() -> str:
    try:
        out = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        return out
    except Exception:
        return "unknown"


def _write_snapshot(path: Path, metrics: dict[str, Any], freeze_ts: str, commit_sha: str, notes: str) -> None:
    doc = {
        "schema_version": "v1.0",
        "frozen": True,
        "freeze_timestamp": freeze_ts,
        "commit_sha": commit_sha,
        "metrics": metrics,
        "notes": notes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    freeze_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    commit_sha = _git_sha()
    ctx = _collect_context()
    baseline, stress, debug = _compute_metrics(ctx)

    _write_snapshot(
        SNAPSHOT_BASELINE,
        baseline,
        freeze_ts,
        commit_sha,
        "Computed from logs/event_bus_live.jsonl + logs/action_card_replay.jsonl via scripts/freeze_stage0_baseline.py",
    )
    _write_snapshot(
        SNAPSHOT_STRESS,
        stress,
        freeze_ts,
        commit_sha,
        "Computed from burst-sensitive latency and gate indicators in local logs.",
    )

    print(json.dumps({"freeze_timestamp": freeze_ts, "commit_sha": commit_sha, "baseline": baseline, "stress": stress, "debug": debug}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
