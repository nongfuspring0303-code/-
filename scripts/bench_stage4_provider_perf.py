#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from market_data_adapter import MarketDataAdapter


def _symbols(n: int) -> List[str]:
    return [f"SYM{i:03d}" for i in range(1, n + 1)]


def _percentile(sorted_values: List[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * p
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return sorted_values[lo]
    weight = rank - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def _fake_primary(symbols: List[str]) -> Dict[str, float]:
    time.sleep(0.003)
    out: Dict[str, float] = {}
    for sym in symbols:
        idx = int(sym[-3:])
        if idx % 5 != 0:
            out[sym] = 100.0 + idx * 0.1
    return out


def _fake_fallback(symbols: List[str]) -> Dict[str, float]:
    time.sleep(0.004)
    out: Dict[str, float] = {}
    for sym in symbols:
        idx = int(sym[-3:])
        if idx % 7 != 0:
            out[sym] = 99.5 + idx * 0.1
    return out


def _build_stage4_adapter() -> MarketDataAdapter:
    cfg = {
        "runtime.price_fetch.cache_ttl_seconds": 120,
        "runtime.price_fetch.max_batch_size": 40,
        "runtime.price_fetch.timeout_seconds": 5,
        "runtime.price_fetch.providers.active": ["primary"],
        "runtime.price_fetch.providers.fallback": ["fallback"],
        "runtime.price_fetch.providers.deprecated": [],
    }
    return MarketDataAdapter(
        config_getter=lambda k, d=None: cfg.get(k, d),
        providers={"primary": _fake_primary, "fallback": _fake_fallback},
    )


def _baseline_fetch(symbols: List[str], timeout_s: float) -> Tuple[Dict[str, float], int]:
    prices: Dict[str, float] = {}
    timeout_count = 0
    for sym in symbols:
        started = time.perf_counter()
        one = _fake_primary([sym])
        if sym in one:
            prices[sym] = one[sym]
        else:
            two = _fake_fallback([sym])
            if sym in two:
                prices[sym] = two[sym]
        elapsed = time.perf_counter() - started
        if elapsed > timeout_s:
            timeout_count += 1
    return prices, timeout_count


def _stage4_fetch(adapter: MarketDataAdapter, symbols: List[str], timeout_s: float) -> Tuple[Dict[str, float], int]:
    started = time.perf_counter()
    prices = adapter.quote_many(symbols)
    elapsed = time.perf_counter() - started
    per_quote_elapsed = elapsed / max(len(symbols), 1)
    timeout_count = len(symbols) if per_quote_elapsed > timeout_s else 0
    return prices, timeout_count


def _summarize(label: str, rounds: int, symbols: List[str], durations_ms: List[float], failures: int, timeouts: int) -> Dict[str, Any]:
    sorted_d = sorted(durations_ms)
    total_quotes = rounds * len(symbols)
    total_seconds = sum(durations_ms) / 1000.0
    return {
        "label": label,
        "rounds": rounds,
        "quotes": total_quotes,
        "throughput_qps": total_quotes / max(total_seconds, 1e-9),
        "latency_ms_p95": _percentile(sorted_d, 0.95),
        "latency_ms_p99": _percentile(sorted_d, 0.99),
        "failure_rate": failures / max(total_quotes, 1),
        "timeout_rate": timeouts / max(total_quotes, 1),
        "avg_latency_ms": statistics.mean(durations_ms) if durations_ms else 0.0,
        "timeout_metric_basis": "per-quote operation timeout (same rule for baseline/stage4)",
    }


def _run_baseline(rounds: int, symbols: List[str], timeout_s: float) -> Dict[str, Any]:
    durations_ms: List[float] = []
    failures = 0
    timeouts = 0
    for _ in range(rounds):
        started = time.perf_counter()
        fetched, timeout_count = _baseline_fetch(symbols, timeout_s)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        durations_ms.append(elapsed_ms)
        failures += len(symbols) - len(fetched)
        timeouts += timeout_count
    return _summarize("baseline_serial", rounds, symbols, durations_ms, failures, timeouts)


def _run_stage4_cold(rounds: int, symbols: List[str], timeout_s: float) -> Dict[str, Any]:
    durations_ms: List[float] = []
    failures = 0
    timeouts = 0
    for _ in range(rounds):
        adapter = _build_stage4_adapter()
        started = time.perf_counter()
        fetched, timeout_count = _stage4_fetch(adapter, symbols, timeout_s)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        durations_ms.append(elapsed_ms)
        failures += len(symbols) - len(fetched)
        timeouts += timeout_count
    return _summarize("stage4_cold", rounds, symbols, durations_ms, failures, timeouts)


def _run_stage4_warm(rounds: int, symbols: List[str], timeout_s: float) -> Dict[str, Any]:
    durations_ms: List[float] = []
    failures = 0
    timeouts = 0
    adapter = _build_stage4_adapter()
    adapter.quote_many(symbols)
    for _ in range(rounds):
        started = time.perf_counter()
        fetched, timeout_count = _stage4_fetch(adapter, symbols, timeout_s)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        durations_ms.append(elapsed_ms)
        failures += len(symbols) - len(fetched)
        timeouts += timeout_count
    return _summarize("stage4_warm", rounds, symbols, durations_ms, failures, timeouts)


def _improvement(base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, float]:
    def ratio(before: float, after: float) -> float:
        if before == 0:
            return 0.0
        return (before - after) / before

    return {
        "throughput_gain": 0.0 if base["throughput_qps"] == 0 else (new["throughput_qps"] - base["throughput_qps"]) / base["throughput_qps"],
        "latency_p95_reduction": ratio(base["latency_ms_p95"], new["latency_ms_p95"]),
        "latency_p99_reduction": ratio(base["latency_ms_p99"], new["latency_ms_p99"]),
        "failure_rate_reduction": ratio(base["failure_rate"], new["failure_rate"]),
        "timeout_rate_reduction": ratio(base["timeout_rate"], new["timeout_rate"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage4 provider performance benchmark with equal-caliber timeout metric and cold/warm split.")
    parser.add_argument("--rounds", type=int, default=60)
    parser.add_argument("--symbols", type=int, default=40)
    parser.add_argument("--timeout-ms", type=float, default=10.0)
    parser.add_argument("--out", type=Path, default=Path("docs/stage5/artifacts/pr88_stage4_perf_benchmark.json"))
    args = parser.parse_args()

    random.seed(42)
    rounds = max(1, args.rounds)
    symbols = _symbols(max(1, args.symbols))
    timeout_s = max(0.001, args.timeout_ms / 1000.0)

    baseline = _run_baseline(rounds, symbols, timeout_s)
    stage4_cold = _run_stage4_cold(rounds, symbols, timeout_s)
    stage4_warm = _run_stage4_warm(rounds, symbols, timeout_s)

    report = {
        "benchmark": "pr88_stage4_provider_perf_equal_caliber",
        "parameters": {
            "rounds": rounds,
            "symbols_per_round": len(symbols),
            "timeout_ms": args.timeout_ms,
            "timeout_metric_basis": "per-quote operation timeout (same rule for baseline/stage4)",
            "baseline": "serial single-symbol fetch primary->fallback",
            "stage4_cold": "MarketDataAdapter batch+cache+failover (fresh adapter each round)",
            "stage4_warm": "MarketDataAdapter batch+cache+failover (adapter warmed, cache reusable)",
        },
        "baseline": baseline,
        "stage4_cold": stage4_cold,
        "stage4_warm": stage4_warm,
        "improvements_vs_baseline": {
            "stage4_cold": _improvement(baseline, stage4_cold),
            "stage4_warm": _improvement(baseline, stage4_warm),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
