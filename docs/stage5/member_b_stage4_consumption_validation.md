# Member B Stage4 Consumption Validation
**Version**: v1.0  
**Date**: 2026-04-24  
**Role**: Member B review / sign-off for Stage4 consumption-side validation  
**Scope**: Consumer impact only after Stage4 provider/batch/cache/failover/queue improvements

## 1) Purpose and boundary

This document defines B-side validation scope for Stage4 outputs after C-side provider and performance changes.

- B validates consumer-side stability and quality.
- B does not own Stage4 provider/queue/perf implementation.

Out-of-scope implementation ownership:

- `MarketDataAdapter`
- batch price fetch
- cache internals
- provider failover internals
- queue/idempotency core implementation
- performance benchmark implementation

## 2) Validation objects

- `sector_candidates`
- `ticker_candidates`
- `A1` (consumed as score signal context)
- `theme_tags`

## 3) Validation dimensions

### 3.1 Field presence

- Required fields must remain present in consumer-facing records.

### 3.2 Type stability

- `sector_candidates` / `ticker_candidates` / `theme_tags` stay as list.
- `A1` stays readable numeric context (`a1_score` in gate summary, `A1` in execution input context).

### 3.3 Null/empty rate

- Null/empty leakage for required consumer fields must not regress unexpectedly.

### 3.4 fallback/default_used ratio

- `market_data_default_used` / `market_data_fallback_used` remain observable.
- Ratio changes can happen for runtime reasons, but semantics must remain interpretable.

### 3.5 manual review ratio

- `WATCH` / `PENDING_CONFIRM` / `BLOCK` paths remain distinguishable from `EXECUTE`.
- Consumer must still be able to explain why a record requires review.

### 3.6 Output quality non-regression

- Provider optimization must not silently break B mapping consumption:
  - fields still readable
  - semantics still interpretable
  - no hidden collapse into unusable placeholders

## 4) Evidence sources for PR88

- C-side Stage4 implementation and gate tests:
  - `tests/test_market_data_adapter.py`
  - `tests/test_member_c_stage4_provider_perf.py`
- B-side Stage4 consumption fixture and validation tests:
  - `tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json`
  - `tests/test_member_b_stage4_consumption_validation.py`

## 5) Sign-off template

> B-side sign-off: PASS / PASS WITH NOTE / FAIL  
> Date: YYYY-MM-DD  
> PR: #<number>  
> Evidence: fixture cases + validation test output + risk notes

## 6) Runtime metric caliber (measured on stable Stage4 implementation)

Measurement basis:

- Fixture: `tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json`
- Runtime validator: `tests/test_member_b_stage4_consumption_validation.py::test_stage4_b_runtime_metrics_snapshot`
- Sample size: 6 executable cases (`B-S4-001` ~ `B-S4-006`)
- Measurement date: 2026-04-24

### 6.1 Definitions

- Null rate:
  - denominator = `sample_size * 4` fields (`sector_candidates`, `ticker_candidates`, `a1_score`, `theme_tags`)
  - numerator = null/empty field observations
- Fallback/default ratios:
  - denominator = `sample_size`
  - numerator = records with `market_data_fallback_used` / `market_data_default_used` evidence
  - evidence source = gate fields when present; otherwise gate `final_reason` tokens
- Manual review ratio:
  - denominator = `sample_size`
  - numerator = final action in `WATCH` / `PENDING_CONFIRM` / `BLOCK`
- Quality degradation threshold:
  - `null_rate <= 1%`
  - `placeholder_leakage_ratio <= 1%`

### 6.2 Measured results

- `null_rate = 0.00%` (0 / 24)
- `fallback_used_ratio = 33.33%` (2 / 6)
- `default_used_ratio = 0.00%` (0 / 6)
- `manual_review_ratio = 33.33%` (2 / 6)
- `placeholder_leakage_ratio = 0.00%` (0 / 6)

### 6.3 Measured conclusion

- Field availability/type stability: PASS
- Fallback/default observability: PASS (fallback paths preserved and reviewable)
- Manual-review path visibility: PASS
- Quality degradation threshold: PASS (`null_rate` and `placeholder_leakage_ratio` both within <=1%)

## 7) Formal B-side sign-off (PR88)

- B-side sign-off: PASS
- Date: 2026-04-24
- PR: #88
- Evidence:
  - fixture cases: `tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json` (`B-S4-001` ~ `B-S4-007`)
  - validation test output: `tests/test_member_b_stage4_consumption_validation.py` and Stage4 companion coverage in `tests/test_member_c_stage4_provider_perf.py`
  - runtime metric results:
    - `null_rate = 0.00%`
    - `fallback_used_ratio = 33.33%`
    - `default_used_ratio = 0.00%`
    - `manual_review_ratio = 33.33%`
    - `placeholder_leakage_ratio = 0.00%`
- Risk notes:
  - Provider optimization did not break `sector_candidates` / `ticker_candidates` / `A1(a1_score)` / `theme_tags` consumer readability or semantics on B fixture coverage.
  - fallback/default/manual-review paths remain interpretable and auditable (`WATCH` reasons preserved, fallback blockers explicit).
  - No observed output-quality degradation on B acceptance metrics (`null_rate` and placeholder leakage both within <=1% threshold).

## 8) Fixture vs Real-window Metrics (parallel view)

### 8.1 Runtime window source (real-window)

- Window source: `captured_local_execution_window` (not production live logs)
- Log types:
  - `decision_gate.jsonl` (primary metrics source)
  - `replay_write.jsonl` (chain continuity)
  - `execution_emit.jsonl` (EXECUTE-path continuity)
- Stats helper: `scripts/member_b_stage4_runtime_window_stats.py`
- Generation command:

```bash
python3 scripts/member_b_stage4_runtime_window_stats.py --pretty
```

- Time range: `2026-04-23T19:44:41.908161Z` ~ `2026-04-23T19:44:41.911011Z`
- Sample size:
  - `decision_gate_count = 6`
  - `replay_write_count = 6`
  - `execution_emit_count = 4`

### 8.2 Metrics comparison (fixture-based vs real-window)

| Metric | Fixture-based | Real-window (captured local execution window) |
| --- | --- | --- |
| null/empty rate | 0.00% | 0.00% |
| fallback_used_ratio | 33.33% | 33.33% |
| default_used_ratio | 0.00% | 0.00% |
| manual_review_ratio | 33.33% | 33.33% |
| placeholder_leakage_ratio | 0.00% | 0.00% |
| quality degradation threshold | PASS | PASS |

### 8.3 Real-window conclusion

- Real-window stats confirm fixture-driven conclusions on the same B-side acceptance dimensions.
- This window is explicitly `captured_local_execution_window`; it strengthens auditability but does not claim online production representativeness.
