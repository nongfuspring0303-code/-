# PR93 Rules-Test Mapping (Governance Patch)

**PR**: #93
**Reviewed Head Baseline**: `76342aa6e20a94549eea891fc4b03c573c943d0c`
**Reviewed At UTC**: `2026-04-27T15:52:53Z`
**Purpose**: close Rule ID ↔ Test ID traceability gap required by PR review template v2.1.

| Rule ID | Rule Statement | Test ID | Test Anchor |
| --- | --- | --- | --- |
| `R93-SEM-001` | Raw semantic missing fields must not be masked by runtime defaults in scorecard output. | `T-R93-SEM-001` | `tests/test_stage5_log_outputs.py::test_stage5_scorecard_marks_semantic_missing_fields_from_raw_output` |
| `R93-PROV-001` | Provider failure/fallback metadata must be persisted into `market_data_provenance.jsonl`. | `T-R93-PROV-001` | `tests/test_stage5_log_outputs.py::test_stage5_market_provenance_includes_provider_failure_metadata` |
| `R93-PROV-002` | Provider metadata must be isolated per trace and must not leak across no-fetch traces. | `T-R93-PROV-002` | `tests/test_stage5_log_outputs.py::test_stage5_market_provenance_does_not_leak_provider_meta_across_traces` |
| `R93-CFG-001` | yfinance path can be used only when explicit feature flag is enabled. | `T-R93-CFG-001` | `tests/test_market_data_adapter.py::test_market_data_adapter_yahoo_prefers_yfinance_before_http` |
| `R93-CFG-002` | Default behavior must keep yfinance disabled to preserve historical `missing-price -> WATCH` semantics. | `T-R93-CFG-002` | `tests/test_market_data_adapter.py::test_market_data_adapter_yahoo_does_not_use_yfinance_by_default` |
| `R93-CFG-003` | Under default config, missing realtime price must remain non-EXECUTE (WATCH path preserved). | `T-R93-CFG-003` | `tests/test_opportunity_score.py::test_missing_realtime_price_forces_watch_with_risk_flag` |
| `R93-CFG-004` | When yfinance is enabled and returns partial symbols, Yahoo HTTP fallback must fill unresolved symbols. | `T-R93-CFG-004` | `tests/test_market_data_adapter.py::test_market_data_adapter_yahoo_merges_yfinance_partial_with_http_fallback` |
| `R93-CFG-005` | yfinance runtime exceptions must not block Yahoo HTTP fallback path. | `T-R93-CFG-005` | `tests/test_market_data_adapter.py::test_market_data_adapter_yahoo_yfinance_exception_still_allows_http_fallback` |
| `R93-SEM-002` | Regression-only: for `event_type=other`, valid semantic `recommended_chain` should still be consumed for template mapping. | `T-R93-SEM-002` | `tests/test_conduction_mapper_dynamic.py::test_conduction_mapper_keeps_semantic_chain_when_event_type_other` |
| `R93-SEM-003` | Regression-only: invalid semantic stock/entity values must be filtered out before `stock_candidates` emission. | `T-R93-SEM-003` | `tests/test_conduction_mapper_dynamic.py::test_conduction_mapper_filters_invalid_semantic_values` |
| `R93-PROV-003` | Provider-level fallback success must be visible in `provider_health_hourly` even when unresolved symbols are empty. | `T-R93-PROV-003` | `tests/test_stage5_log_outputs.py::test_stage5_market_provenance_tracks_provider_fallback_success` |

## Related Source-of-Truth Updates

- semantic contract boundary update: `docs/semantic-baseline-contract-v1.md`
- metric registration update: `configs/metric_dictionary.yaml`
- runtime config explicit flag: `configs/edt-modules-config.yaml`
