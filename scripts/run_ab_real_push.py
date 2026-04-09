#!/usr/bin/env python3
"""Run A/B real computation and push event/sector/opportunity to C ingest API."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
import os
from typing import Any, Dict, List
from urllib import request

from data_adapter import DataAdapter
from full_workflow_runner import FullWorkflowRunner


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-EDT-Token": os.getenv("EDT_API_TOKEN", os.getenv("EDT_WS_TOKEN", "edt-local-dev-token")),
        },
        method="POST",
    )
    with request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _num_or_default(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_sector_update(conduction: Dict[str, Any], trace_id: str, request_id: str, batch_id: str, ts: str) -> Dict[str, Any]:
    sectors: List[Dict[str, Any]] = []
    for item in conduction.get("sector_impacts", []):
        direction_raw = str(item.get("direction", "WATCH")).lower()
        if direction_raw in {"benefit", "long"}:
            direction = "LONG"
        elif direction_raw in {"hurt", "short"}:
            direction = "SHORT"
        else:
            direction = "WATCH"

        sectors.append(
            {
                "name": item.get("sector", "未知板块"),
                "direction": direction,
                "impact_score": round(min(1.0, max(0.0, float(conduction.get("confidence", 0)) / 100.0)), 2),
                "confidence": round(min(1.0, max(0.0, float(conduction.get("confidence", 0)) / 100.0)), 2),
            }
        )

    chain = []
    for idx, name in enumerate(conduction.get("conduction_path", [])):
        if idx == 0:
            level = "macro"
        elif idx == len(conduction.get("conduction_path", [])) - 1:
            level = "theme"
        else:
            level = "sector"
        chain.append({"level": level, "name": str(name), "relation": "affects_below"})

    return {
        "type": "sector_update",
        "trace_id": trace_id,
        "request_id": request_id,
        "batch_id": batch_id,
        "schema_version": "v1.0",
        "sectors": sectors,
        "conduction_chain": chain,
        "timestamp": ts,
    }


def normalize_event_update(result: Dict[str, Any], trace_id: str, request_id: str, batch_id: str, ts: str) -> Dict[str, Any]:
    intel = result.get("intel", {})
    event_object = intel.get("event_object", {})
    severity = intel.get("severity", {})
    signal = result.get("analysis", {}).get("signal", {})
    return {
        "type": "event_update",
        "trace_id": trace_id,
        "request_id": request_id,
        "batch_id": batch_id,
        "schema_version": "v1.0",
        "headline": event_object.get("headline", "A/B 实时计算事件"),
        "source": event_object.get("source_url", "A-Module"),
        "severity": event_object.get("severity", severity.get("severity", "E3")),
        "evidence_score": severity.get("A0", 0),
        "narrative_state": signal.get("narrative_mode", "Fact-Driven"),
        "timestamp": event_object.get("detected_at", ts),
    }


def normalize_opportunity_update(result: Dict[str, Any], trace_id: str, request_id: str, batch_id: str, ts: str) -> Dict[str, Any]:
    opp = result.get("analysis", {}).get("opportunity_update", {})
    payload = {
        "type": "opportunity_update",
        "trace_id": trace_id,
        "request_id": request_id,
        "batch_id": batch_id,
        "schema_version": "v1.0",
        "opportunities": opp.get("opportunities", []),
        "timestamp": opp.get("timestamp", ts),
    }
    return payload


def one_cycle(api_base: str, require_live: bool = False) -> None:
    adapter = DataAdapter()
    runner = FullWorkflowRunner()

    raw = adapter.fetch()
    news = raw.get("news", {})
    market = raw.get("market_data", {})
    sector_data = raw.get("sector_data", [])
    if require_live and (news.get("metadata", {}).get("is_test_data") or market.get("is_test_data")):
        raise RuntimeError("live source unavailable: adapter returned test data")

    payload = {
        "headline": news.get("headline", ""),
        "source": news.get("source_url", news.get("source", "")),
        "timestamp": news.get("timestamp", utc_now_iso()),
        "summary": news.get("raw_text", news.get("headline", "")),
        "vix": _num_or_default(market.get("vix_level"), None),
        "vix_change_pct": _num_or_default(market.get("vix_change_pct"), None),
        "spx_move_pct": _num_or_default(market.get("spx_change_pct"), None),
        "sector_move_pct": _num_or_default(market.get("etf_volatility", {}).get("change_pct"), None),
        "sequence": 1,
        "sector_data": sector_data,
    }

    result = runner.run(payload)
    event_id = result.get("intel", {}).get("event_object", {}).get("event_id", "evt_ab_real_001")
    trace_id = str(result.get("trace_id") or event_id)
    request_id = str(result.get("request_id") or trace_id)
    batch_id = str(result.get("batch_id") or f"BATCH-{request_id}")
    ts = utc_now_iso()

    event_update = normalize_event_update(result, trace_id, request_id, batch_id, ts)
    sector_update = normalize_sector_update(result.get("analysis", {}).get("conduction", {}), trace_id, request_id, batch_id, ts)
    opportunity_update = normalize_opportunity_update(result, trace_id, request_id, batch_id, ts)

    print("[AB] trace_id:", trace_id)
    print("[AB] request_id:", request_id)
    print("[AB] batch_id:", batch_id)
    print("[AB] headline:", event_update.get("headline"))
    print("[AB] sectors:", len(sector_update.get("sectors", [])))
    print("[AB] opportunities:", len(opportunity_update.get("opportunities", [])))

    r1 = post_json(f"{api_base}/api/ingest/event-update", event_update)
    r2 = post_json(f"{api_base}/api/ingest/sector-update", sector_update)
    r3 = post_json(f"{api_base}/api/ingest/opportunity-update", opportunity_update)

    print("[C-INGEST] event-update:", r1)
    print("[C-INGEST] sector-update:", r2)
    print("[C-INGEST] opportunity-update:", r3)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run A/B real computation and push to C ingest")
    default_api = f"http://127.0.0.1:{os.getenv('EDT_API_PORT', '18787')}"
    parser.add_argument("--api", default=default_api, help="C ingest API base")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between cycles in loop mode")
    parser.add_argument("--require-live", action="store_true", help="Only push when live (non-fallback) news is available")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.loop:
        one_cycle(args.api, require_live=args.require_live)
        return 0

    while True:
        try:
            one_cycle(args.api, require_live=args.require_live)
        except Exception as exc:
            print("[AB] cycle failed:", exc)
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
