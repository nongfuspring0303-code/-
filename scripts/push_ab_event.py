#!/usr/bin/env python3
"""
向 C 模块 ingest 接口推送 A/B 事件（用于联调）。

示例：
  python3 scripts/push_ab_event.py --type sector-update
  python3 scripts/push_ab_event.py --type opportunity-update --trace-id evt_demo_123
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from urllib import request


def post(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=5) as resp:
        body = resp.read().decode("utf-8")
    return body


def build_payload(kind: str, trace_id: str):
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    if kind == "event-update":
        return {
            "trace_id": trace_id,
            "schema_version": "v1.0",
            "headline": "A 模块联调事件",
            "source": "A-Module",
            "severity": "E2",
            "timestamp": now,
        }
    if kind == "sector-update":
        return {
            "trace_id": trace_id,
            "schema_version": "v1.0",
            "sectors": [
                {"name": "科技", "direction": "LONG", "impact_score": 0.83, "confidence": 0.9},
                {"name": "金融", "direction": "WATCH", "impact_score": 0.41, "confidence": 0.72},
            ],
            "conduction_chain": [
                {"level": "macro", "name": "流动性", "relation": "affects_above"},
                {"level": "sector", "name": "科技", "relation": "same"},
                {"level": "theme", "name": "算力", "relation": "affects_below"},
            ],
            "timestamp": now,
        }
    return {
        "trace_id": trace_id,
        "schema_version": "v1.0",
        "opportunities": [
            {
                "symbol": "NVDA",
                "name": "英伟达",
                "sector": "科技",
                "signal": "LONG",
                "entry_zone": {"support": 1120, "resistance": 1180},
                "risk_flags": [{"type": "volatility", "level": "medium", "description": "波动较大"}],
                "final_action": "PENDING_CONFIRM",
                "reasoning": "板块趋势延续",
                "confidence": 0.86,
            }
        ],
        "timestamp": now,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument(
        "--type",
        required=True,
        choices=["event-update", "sector-update", "opportunity-update"],
    )
    parser.add_argument("--trace-id", default="evt_ab_demo_001")
    args = parser.parse_args()

    payload = build_payload(args.type, args.trace_id)
    url = f"{args.api}/api/ingest/{args.type}"
    print(post(url, payload))


if __name__ == "__main__":
    main()
