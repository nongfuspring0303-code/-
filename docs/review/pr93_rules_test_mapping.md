# PR93 Rules-Test Mapping (Governance Patch)

**PR**: #93
**Reviewed Head Baseline**: `13655953d48b66b25f789d79e6c0ed32b3578038`
**Purpose**: close Rule ID ↔ Test ID traceability gap required by PR review template v2.1.

| Rule ID | Rule Statement | Test ID | Test Anchor |
| --- | --- | --- | --- |
| `R93-SEM-001` | Raw semantic missing fields must not be masked by runtime defaults in scorecard output. | `T-R93-SEM-001` | `tests/test_stage5_log_outputs.py::test_stage5_scorecard_marks_semantic_missing_fields_from_raw_output` |
| `R93-PROV-001` | Provider failure/fallback metadata must be persisted into `market_data_provenance.jsonl`. | `T-R93-PROV-001` | `tests/test_stage5_log_outputs.py::test_stage5_market_provenance_includes_provider_failure_metadata` |
| `R93-PROV-002` | Provider metadata must be isolated per trace and must not leak across no-fetch traces. | `T-R93-PROV-002` | `tests/test_stage5_log_outputs.py::test_stage5_market_provenance_does_not_leak_provider_meta_across_traces` |
| `R93-CFG-001` | yfinance path can be used only when explicit feature flag is enabled. | `T-R93-CFG-001` | `tests/test_market_data_adapter.py::test_market_data_adapter_yahoo_prefers_yfinance_before_http` |
| `R93-CFG-002` | Default behavior must keep yfinance disabled to preserve historical `missing-price -> WATCH` semantics. | `T-R93-CFG-002` | `tests/test_market_data_adapter.py::test_market_data_adapter_yahoo_does_not_use_yfinance_by_default` |

## Related Source-of-Truth Updates

- semantic contract boundary update: `docs/semantic-baseline-contract-v1.md`
- metric registration update: `configs/metric_dictionary.yaml`
- runtime config explicit flag: `configs/edt-modules-config.yaml`
