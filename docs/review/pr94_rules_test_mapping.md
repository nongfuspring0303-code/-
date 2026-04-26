# PR94 Rule-Test Mapping

Head reviewed: ffc137165bb2858fa5b8da2f43c1702a9713f20a (2026-04-27)
Review basis: latest diff at review time; SHA refers to review commit, not head

## R-C-S5-PR94-001 Market Provenance Fields
- Rule statement: `market_data_provenance.jsonl` must include extended provider-call fields and track missing fields without fabrication.
- Code anchor: `scripts/full_workflow_runner.py` (`provenance_record` fields + `provenance_field_missing` population).
- Test ID: `T-C-S5-PR94-PROV-MISSING`
- Test anchor: `tests/test_residual_evidence_logging_gaps.py::test_residual_market_data_provenance_fields_are_extended_and_missing_tracked`
- Assertion summary: extended fields exist; unavailable provider fields are `None`/`[]`; missing list includes absent fields.

## R-C-S5-PR94-002 Market Provenance Positive Path
- Rule statement: when provider metadata is present in payload, provenance must preserve those values; symbols prefer payload fields.
- Code anchor: `scripts/full_workflow_runner.py` (payload-first `symbols_requested`/`symbols_returned` semantics).
- Test ID: `T-C-S5-PR94-PROV-PASS`
- Test anchor: `tests/test_residual_evidence_logging_gaps.py::test_residual_market_data_provenance_prefers_payload_symbols_and_metadata`
- Assertion summary: provider metadata is written as-is; symbols are normalized and not flagged missing.

## R-C-S5-PR94-003 Decision Gate Structured Fail Path
- Rule statement: non-`EXECUTE` gate results must include structured `reject_reason_code` and `reject_reason_text`.
- Code anchor: `scripts/workflow_runner.py` (`_derive_gate_result`, `_derive_reject_reason_code`, `_log_decision_gate`).
- Test ID: `T-C-S5-PR94-GATE-FAIL`
- Test anchor: `tests/test_residual_evidence_logging_gaps.py::test_residual_decision_gate_prepost_and_hard_rules_are_structured`
- Assertion summary: fail-path scenarios produce structured gate fields and expected reject codes.

## R-C-S5-PR94-004 Decision Gate EXECUTE Pass Contract
- Rule statement: `EXECUTE` records must produce `gate_result=PASS` and null reject fields.
- Code anchor: `scripts/workflow_runner.py` (`_derive_gate_result`, `_derive_reject_reason_code`, `_log_decision_gate`).
- Test ID: `T-C-S5-PR94-GATE-PASS`
- Test anchor: `tests/test_residual_evidence_logging_gaps.py::test_residual_decision_gate_execute_path_is_pass_with_null_reject_fields`
- Assertion summary: execute path stays `EXECUTE`; `gate_result=PASS`; reject fields are null.

## R-C-S5-PR94-005 Replay/Execution Health Aggregation
- Rule statement: evaluator must consume replay/execution logs and emit replay health metrics in daily output.
- Code anchor: `scripts/system_log_evaluator.py` (`replay_execution_health` aggregation).
- Test ID: `T-C-S5-PR94-REPLAY-HEALTH`
- Test anchor: `tests/test_residual_evidence_logging_gaps.py::test_residual_evaluator_replay_execution_health_detects_missing_links`
- Assertion summary: replay/execution counters and separation rate are emitted with expected values.
