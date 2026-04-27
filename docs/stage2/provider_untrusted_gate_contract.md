# Provider Untrusted Gate Contract (PR95)

Date: 2026-04-26
Scope: provider trust execution hardening only.

## Rule Identity
- Rule ID: `R-A-S2-ProviderTrustGate`
- Owner: A (primary), B/C (joint review touchpoint)

## Trigger Condition
- `provider_untrusted == true` in `WorkflowRunner` input payload.

## Expected Behavior
- Output gate must block `EXECUTE`.
- Final action must be non-`EXECUTE` (`WATCH`/`BLOCK`/`PENDING_CONFIRM` according to existing gate logic).
- `decision_gate.output_gate.blockers` must include `provider_untrusted`.

## Logging Evidence Requirements
- `decision_gate.jsonl` must persist:
  - `final_action`
  - `output_gate.blockers` (including `provider_untrusted`)
  - correlation fields (`request_id`, `batch_id`, `event_hash`, `trace_id`)

## Code/Test Anchors
- Code anchor: `scripts/workflow_runner.py::_evaluate_output_gate`
- Test ID: `T-C-S2-ProviderUntrusted-Block`
- Test anchor: `tests/test_member_c_stage2_blocker_evidence.py::test_stage2_c_provider_untrusted_is_blocked_by_output_gate`

## Non-Goals
- No changes to Stage5 residual evidence logging fields.
- No changes to scorecard/evaluator/dashboard.
- No changes to market data provider collection implementation.
