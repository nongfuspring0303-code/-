# Residual Evidence Logging Contract (PR94)

Date: 2026-04-26
Scope: residual evidence logging only (no execution-strategy changes).

## 1. `market_data_provenance.jsonl`

Required fields:
- `market_data_provider`
- `provider_path`
- `symbols_requested`
- `symbols_returned`
- `request_mode`
- `fetch_latency_ms`
- `market_data_ts`
- `market_data_delay_seconds`
- `rate_limited`
- `http_status`
- `error_code`
- `used_by_module`
- `provenance_field_missing`

Rules:
- Unavailable provider-call fields must be written as `null` or `[]`.
- Every unavailable field must be listed in `provenance_field_missing`.
- Provider-call fields must not be fabricated.
- `symbols_requested` / `symbols_returned` semantics:
  - Prefer `payload.symbols_requested` / `payload.symbols_returned` when present.
  - Fallback to `MarketValidator` consumed-symbol inference when payload fields are absent.

## 2. `decision_gate.jsonl`

Required fields:
- `final_action_before_gate`
- `final_action_after_gate`
- `gate_result`
- `triggered_rules`
- `reject_reason_code`
- `reject_reason_text`

Rules:
- `EXECUTE => gate_result = PASS`.
- `EXECUTE => reject_reason_code = null`.
- Non-`EXECUTE` records must contain structured `reject_reason_code` and `reject_reason_text`.

## 3. `system_health_daily.json`

Required nested fields:
- `replay_execution_health.replay_write_count`
- `replay_execution_health.execution_emit_count`
- `replay_execution_health.orphan_replay_count`
- `replay_execution_health.execute_without_replay_count`
- `replay_execution_health.execute_without_gate_count`
- `replay_execution_health.replay_execution_separation_rate`

Rules:
- Evaluator must consume `replay_write.jsonl` and `execution_emit.jsonl`.
- `replay_execution_health` must be emitted daily even when anomaly counts are zero.
