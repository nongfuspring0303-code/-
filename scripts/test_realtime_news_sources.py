#!/usr/bin/env python3
"""Capability test for Sina and Finnhub realtime news ingestion.

This script is standalone and does not modify project runtime behavior.
It validates whether each source can return fresh news within a time window.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests


SINA_API_URL = "http://zhibo.sina.com.cn/api/zhibo/feed"
SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://finance.sina.com.cn/7x24/",
}

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_to_utc(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass
class SourceStats:
    name: str
    attempts: int = 0
    success: int = 0
    failed: int = 0
    latency_ms: List[float] = field(default_factory=list)
    fresh_hits: int = 0
    error_samples: List[str] = field(default_factory=list)

    def record_success(self, latency_ms: float) -> None:
        self.attempts += 1
        self.success += 1
        self.latency_ms.append(latency_ms)

    def record_failure(self, latency_ms: float, err: str) -> None:
        self.attempts += 1
        self.failed += 1
        self.latency_ms.append(latency_ms)
        if len(self.error_samples) < 5:
            self.error_samples.append(err)

    def to_dict(self) -> Dict[str, Any]:
        p50 = statistics.median(self.latency_ms) if self.latency_ms else None
        p95 = None
        if self.latency_ms:
            sorted_vals = sorted(self.latency_ms)
            idx = int(max(0, min(len(sorted_vals) - 1, round(0.95 * (len(sorted_vals) - 1)))))
            p95 = sorted_vals[idx]
        return {
            "name": self.name,
            "attempts": self.attempts,
            "success": self.success,
            "failed": self.failed,
            "success_rate": round(self.success / self.attempts, 4) if self.attempts else 0.0,
            "fresh_hits": self.fresh_hits,
            "latency_ms_p50": round(p50, 2) if p50 is not None else None,
            "latency_ms_p95": round(p95, 2) if p95 is not None else None,
            "error_samples": self.error_samples,
        }


def fetch_sina(session: requests.Session, timeout: int) -> Tuple[List[Dict[str, Any]], float]:
    params = {
        "page": 1,
        "page_size": 20,
        "zhibo_id": 152,
        "tag_id": 0,
        "dire": "f",
        "dpc": 1,
        "pagesize": 20,
    }
    t0 = time.perf_counter()
    resp = session.get(SINA_API_URL, params=params, headers=SINA_HEADERS, timeout=timeout)
    latency_ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    payload = resp.json()
    items = (((payload.get("result") or {}).get("data") or {}).get("feed") or {}).get("list") or []
    if not isinstance(items, list):
        items = []
    return items, latency_ms


def fetch_finnhub(session: requests.Session, timeout: int, symbol: str, api_key: str) -> Tuple[List[Dict[str, Any]], float]:
    end_date = now_utc().date()
    start_date = end_date - timedelta(days=1)
    params = {
        "symbol": symbol,
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "token": api_key,
    }
    t0 = time.perf_counter()
    resp = session.get(FINNHUB_URL, params=params, timeout=timeout)
    latency_ms = (time.perf_counter() - t0) * 1000
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected payload type: {type(data).__name__}")
    return data, latency_ms


def run_test(
    duration_minutes: int,
    interval_seconds: int,
    timeout_seconds: int,
    finnhub_symbols: List[str],
    finnhub_api_key: str,
    skip_finnhub: bool,
) -> Dict[str, Any]:
    session = requests.Session()
    deadline = time.time() + duration_minutes * 60
    poll_idx = 0

    sina_stats = SourceStats(name="sina")
    finnhub_stats = SourceStats(name="finnhub")

    seen_sina_ids: Set[int] = set()
    seen_finnhub_news: Set[str] = set()
    sina_new_items = 0
    finnhub_new_items = 0
    sina_latest_ts: Optional[datetime] = None
    finnhub_latest_ts: Optional[datetime] = None

    while time.time() < deadline:
        poll_idx += 1
        tick_started = now_utc()

        # Sina
        try:
            sina_items, latency = fetch_sina(session, timeout_seconds)
            sina_stats.record_success(latency)
            max_ts_in_poll = sina_latest_ts
            for item in sina_items:
                item_id = item.get("id")
                if isinstance(item_id, int) and item_id not in seen_sina_ids:
                    seen_sina_ids.add(item_id)
                    sina_new_items += 1

                created = str(item.get("create_time") or "")
                dt = parse_iso_to_utc(created)
                if dt and (max_ts_in_poll is None or dt > max_ts_in_poll):
                    max_ts_in_poll = dt

            sina_latest_ts = max_ts_in_poll
            if sina_latest_ts:
                lag = (now_utc() - sina_latest_ts).total_seconds()
                if lag <= 300:
                    sina_stats.fresh_hits += 1
        except Exception as exc:  # noqa: BLE001
            sina_stats.record_failure(0.0, str(exc))

        # Finnhub
        if not skip_finnhub:
            for symbol in finnhub_symbols:
                try:
                    rows, latency = fetch_finnhub(session, timeout_seconds, symbol, finnhub_api_key)
                    finnhub_stats.record_success(latency)
                    max_ts = finnhub_latest_ts
                    for row in rows:
                        url = str(row.get("url") or "")
                        dt_val = row.get("datetime")
                        dt = None
                        if isinstance(dt_val, (int, float)):
                            dt = datetime.fromtimestamp(float(dt_val), tz=timezone.utc)
                        elif isinstance(dt_val, str):
                            dt = parse_iso_to_utc(dt_val)
                        key = f"{symbol}|{url}|{dt.isoformat() if dt else ''}"
                        if key and key not in seen_finnhub_news:
                            seen_finnhub_news.add(key)
                            finnhub_new_items += 1
                        if dt and (max_ts is None or dt > max_ts):
                            max_ts = dt
                    finnhub_latest_ts = max_ts
                    if finnhub_latest_ts:
                        lag = (now_utc() - finnhub_latest_ts).total_seconds()
                        if lag <= 300:
                            finnhub_stats.fresh_hits += 1
                except Exception as exc:  # noqa: BLE001
                    finnhub_stats.record_failure(0.0, f"{symbol}: {exc}")

        elapsed = (now_utc() - tick_started).total_seconds()
        sleep_for = max(0.0, interval_seconds - elapsed)
        if sleep_for > 0:
            time.sleep(sleep_for)

    result = {
        "started_at": datetime.fromtimestamp(deadline - duration_minutes * 60, tz=timezone.utc).isoformat(),
        "ended_at": now_utc().isoformat(),
        "duration_minutes": duration_minutes,
        "interval_seconds": interval_seconds,
        "poll_cycles": poll_idx,
        "sources": {
            "sina": {
                **sina_stats.to_dict(),
                "unique_new_items": sina_new_items,
                "latest_news_ts": sina_latest_ts.isoformat() if sina_latest_ts else None,
                "freshness_lag_seconds": round((now_utc() - sina_latest_ts).total_seconds(), 1) if sina_latest_ts else None,
            },
            "finnhub": {
                **finnhub_stats.to_dict(),
                "unique_new_items": finnhub_new_items,
                "latest_news_ts": finnhub_latest_ts.isoformat() if finnhub_latest_ts else None,
                "freshness_lag_seconds": round((now_utc() - finnhub_latest_ts).total_seconds(), 1)
                if finnhub_latest_ts
                else None,
                "symbols": finnhub_symbols,
                "skipped": skip_finnhub,
            },
        },
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test realtime capability for Sina and Finnhub news sources.")
    parser.add_argument("--duration-minutes", type=int, default=10, help="Test window in minutes (default: 10)")
    parser.add_argument("--interval-seconds", type=int, default=30, help="Polling interval seconds (default: 30)")
    parser.add_argument("--timeout-seconds", type=int, default=10, help="HTTP timeout per request")
    parser.add_argument(
        "--finnhub-symbols",
        type=str,
        default="AAPL,MSFT,NVDA",
        help="Comma-separated symbols for Finnhub test",
    )
    parser.add_argument(
        "--finnhub-api-key",
        type=str,
        default=os.getenv("FINNHUB_API_KEY", ""),
        help="Finnhub API key (or env FINNHUB_API_KEY)",
    )
    parser.add_argument("--skip-finnhub", action="store_true", help="Skip Finnhub tests")
    parser.add_argument("--out", type=str, default="", help="Optional output json file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [x.strip().upper() for x in args.finnhub_symbols.split(",") if x.strip()]
    skip_finnhub = args.skip_finnhub or not args.finnhub_api_key

    if not skip_finnhub and not symbols:
        print("[ERROR] finnhub symbols are required unless --skip-finnhub", file=sys.stderr)
        return 2

    if skip_finnhub:
        print("[INFO] Finnhub test disabled (missing key or --skip-finnhub).")

    result = run_test(
        duration_minutes=max(1, args.duration_minutes),
        interval_seconds=max(5, args.interval_seconds),
        timeout_seconds=max(3, args.timeout_seconds),
        finnhub_symbols=symbols,
        finnhub_api_key=args.finnhub_api_key,
        skip_finnhub=skip_finnhub,
    )

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(rendered)
            f.write("\n")
        print(f"[INFO] Wrote result to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
