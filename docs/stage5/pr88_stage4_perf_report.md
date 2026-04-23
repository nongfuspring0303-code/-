# PR88 Stage4 Provider/Performance Benchmark Report

- Date: 2026-04-24
- Scope: Stage4 C-side provider adapter + batch/cache/failover performance evidence
- Script: `scripts/bench_stage4_provider_perf.py`
- Artifact: `docs/stage5/artifacts/pr88_stage4_perf_benchmark.json`
- Runtime-window script: `scripts/collect_stage4_runtime_window_metrics.py`
- Runtime-window artifact: `docs/stage5/artifacts/pr88_stage4_runtime_window_metrics.json`

## 1) Method

- Baseline model: serial single-symbol fetch (`primary -> fallback`), no batch/cache reuse.
- Stage4 cold model: `MarketDataAdapter` batch fetch + cache + failover (fresh adapter each round).
- Stage4 warm model: `MarketDataAdapter` batch fetch + cache + failover (single adapter + cache reusable).
- Parameters:
  - rounds: 60
  - symbols per round: 40
  - timeout threshold: 10ms
  - timeout metric basis: **per-quote operation timeout (same rule for baseline/stage4)**

Command:

```bash
python3 scripts/bench_stage4_provider_perf.py --rounds 60 --symbols 40 --timeout-ms 10
```

## 2) Measured Results

- Baseline
  - throughput: `213.68 qps`
  - P95 latency: `189.54 ms`
  - P99 latency: `190.47 ms`
  - failure_rate: `2.50%`
  - timeout_rate: `0.0417%`
- Stage4 (cold)
  - throughput: `4571.23 qps`
  - P95 latency: `9.16 ms`
  - P99 latency: `9.50 ms`
  - failure_rate: `2.50%`
  - timeout_rate: `0.00%`
- Stage4 (warm)
  - throughput: `4581.03 qps`
  - P95 latency: `9.04 ms`
  - P99 latency: `9.05 ms`
  - failure_rate: `2.50%`
  - timeout_rate: `0.00%`

## 3) Improvement Summary

- vs Baseline -> Stage4 cold
  - Throughput gain: `+2039.27%` (about `21.39x`)
  - P95 latency reduction: `95.17%`
  - P99 latency reduction: `95.01%`
  - Failure rate reduction: `0.00%` (unchanged under same data availability assumptions)
  - Timeout rate reduction: `100.00%` (`0.0417% -> 0.00%`)
- vs Baseline -> Stage4 warm
  - Throughput gain: `+2043.86%` (about `21.44x`)
  - P95 latency reduction: `95.23%`
  - P99 latency reduction: `95.25%`
  - Failure rate reduction: `0.00%`
  - Timeout rate reduction: `100.00%`

## 4) Runtime Window Metrics (decision/replay/execution logs)

- Window mode: generated runtime window from fixture payloads, then measured on real JSONL logs.
- Data source logs:
  - `decision_gate.jsonl`
  - `replay_write.jsonl`
  - `execution_emit.jsonl`
- Generation parameters:
  - fixture cases: 6
  - rounds: 5
  - total runs: 30
- Window snapshot:
  - decision rows: `30`
  - replay rows: `30`
  - execution rows: `20`
  - fallback_used_ratio: `33.33%`
  - default_used_ratio: `0.00%`
  - manual_review_ratio: `33.33%`
  - execution ids missing in replay: `0` (alignment_ok=`true`)

Command:

```bash
python3 scripts/collect_stage4_runtime_window_metrics.py --rounds 5 \
  --out docs/stage5/artifacts/pr88_stage4_runtime_window_metrics.json
```

## 5) Semantics Safety Checks (no regression)

- Stage4 gate tests:
  - `tests/test_member_c_stage4_provider_perf.py::test_dual_write_backward_compat_test`
  - `tests/test_member_c_stage4_provider_perf.py::test_priority_queue_order_semantics_test`
  - `tests/test_member_c_stage4_provider_perf.py::test_idempotent_replay_write_test`
- Provider behavior tests:
  - `tests/test_market_data_adapter.py`
- Config-runtime alignment guard:
  - `tests/test_opportunity_score.py::test_price_fetch_disabled_does_not_call_adapter`

Validation command:

```bash
python3 -m pytest -q \
  tests/test_market_data_adapter.py \
  tests/test_member_c_stage4_provider_perf.py \
  tests/test_opportunity_score.py::test_price_fetch_disabled_does_not_call_adapter
```

Result: `11 passed`

## 6) Conclusion

- Stage4 C-side performance objective is met with clear improvement on throughput and tail latency under equal timeout metric basis.
- Cold/warm split is now explicit, avoiding mixed-cache interpretation risk.
- Runtime-window metrics are now available from decision/replay/execution logs to support downstream B-side quality discussion.
- Queue/idempotency/compatibility checks pass under current test gate.
- No new config-runtime bypass found for `price_fetch.enabled=false` after guard test.
