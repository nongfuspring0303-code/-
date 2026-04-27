# PR95 Rule-Test Mapping

Review Scope: Latest PR head at review time
Reviewed At (UTC): 2026-04-27

## R-A-S2-ProviderTrustGate
- Rule statement: when `provider_untrusted=true`, output gate must block `EXECUTE`.
- Code anchor: `scripts/workflow_runner.py::_evaluate_output_gate` (`provider_untrusted` blocker).
- Test ID: `T-C-S2-ProviderUntrusted-Block`
- Test anchor: `tests/test_member_c_stage2_blocker_evidence.py::test_stage2_c_provider_untrusted_is_blocked_by_output_gate`
- Assertion summary: final action is non-`EXECUTE`; `decision_gate.output_gate.blockers` includes `provider_untrusted`.

## R-C-S2-DecisionGateEvidence
- Rule statement: blocker path must retain structured gate evidence in `decision_gate.jsonl`.
- Code anchor: `scripts/workflow_runner.py::_log_decision_gate`.
- Test ID: `T-C-S2-DecisionGate-BlockerEvidence`
- Test anchor: `tests/test_member_c_stage2_blocker_evidence.py::test_stage2_c_decision_gate_has_blocker_evidence`
- Assertion summary: blocker event persists request/batch/event_hash and gate blockers in decision gate log.

## R-C-S2-ProvenanceOnBlockerPath
- Rule statement: provenance fields must persist on blocker path (non-EXECUTE).
- Code anchor: `scripts/full_workflow_runner.py` (market_data_provenance logging).
- Test ID: `T-C-S2-ProvenanceOnBlockerPath`
- Test anchor: `tests/test_member_c_stage2_blocker_evidence.py::test_stage2_c_provenance_fields_persist_on_blocker_path`
- Assertion summary: market_data_provenance.jsonl persists trace/correlation fields on non-EXECUTE path.

## R-C-S2-BlockerPathNoExecutionEmit
- Rule statement: blocker path must not emit execution_emit records.
- Code anchor: `scripts/workflow_runner.py` (execution emit skipped on blocker path).
- Test ID: `T-C-S2-BlockerPathNoExecutionEmit`
- Test anchor: `tests/test_member_c_stage2_blocker_evidence.py::test_stage2_c_blocker_path_no_execution_emit_and_replay_written`
- Assertion summary: execution_emit.jsonl is empty on blocker path; replay_write.jsonl retains evidence.

## R-C-S2-ReplayDurableBeforeReturn
- Rule statement: replay_write must be durable before run() returns (no fire-and-forget).
- Code anchor: `scripts/workflow_runner.py::_log_replay_task`.
- Test ID: `T-C-S2-ReplayDurableBeforeReturn`
- Test anchor: `tests/test_member_c_stage2_blocker_evidence.py::test_stage2_c_replay_write_durable_before_run_return`
- Assertion summary: replay_write.jsonl is readable immediately after run() returns, even with delayed _log_replay_task.
