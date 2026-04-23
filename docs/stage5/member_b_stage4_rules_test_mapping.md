# Member B Stage4 Rules-Test Mapping
**Version**: v1.0  
**Date**: 2026-04-24  
**Role**: Member B review / sign-off for Stage4 consumption-side validation  
**Scope**: Consumer-side non-regression after provider/batch/cache/failover/queue optimization

## Rules

### R-B-S4-001
- Rule statement: provider optimization must not break `sector_candidates` consumption.
- Test anchor:
  - `tests/test_member_b_stage4_consumption_validation.py::test_stage4_b_consumption_cases_preserve_summary_fields`

### R-B-S4-002
- Rule statement: provider optimization must not break `ticker_candidates` consumption.
- Test anchor:
  - `tests/test_member_b_stage4_consumption_validation.py::test_stage4_b_consumption_cases_preserve_summary_fields`

### R-B-S4-003
- Rule statement: provider optimization must not introduce semantic drift in `A1` / `theme_tags`.
- Test anchor:
  - `tests/test_member_b_stage4_consumption_validation.py::test_stage4_b_a1_theme_tags_semantics_stable`

### R-B-S4-004
- Rule statement: batch/cache/failover/queue optimization must not significantly degrade consumer-side quality.
- Test anchor:
  - `tests/test_member_b_stage4_consumption_validation.py::test_stage4_b_quality_guardrails`
  - `tests/test_member_b_stage4_consumption_validation.py::test_stage4_b_runtime_metrics_snapshot`
  - `tests/test_member_c_stage4_provider_perf.py::test_priority_queue_order_semantics_test`
  - `tests/test_member_c_stage4_provider_perf.py::test_idempotent_replay_write_test`

## Joint review touchpoints

### A-side touchpoints

- dual-write backward compatibility
- queue/order/idempotency contract boundaries
- state-machine and Gate semantics remain intact

### C-side touchpoints

- provider/batch/cache/failover implementation behavior
- queue order and idempotency runtime semantics
- perf baseline evidence generation

### B-side independent closure

- consumer field presence/type checks
- fallback/default/review observability checks
- consumption quality non-regression checks
