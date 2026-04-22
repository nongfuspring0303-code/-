# EDT Fix Baseline Snapshot (2026-04-21)

Status: FROZEN-VALUES (computed from reproducible local logs)
Owner: Phase 0 execution owner = Member A; Member B/C review & sign-off only

## Metric Schema
- `missing_opportunity_but_execute_rate`
- `fallback_leak_rate`
- `financial_rate`
- `sectors_non_whitelist_rate`
- `replay_primary_key_completeness`
- `trace_join_success_rate`
- `event_without_sector_rate`
- `p95_decision_latency`
- `same_trace_ai_duplicate_call_rate`

## Stress Baseline Schema
- `queue_backlog_peak`
- `raw_ingest_to_event_update_p95`
- `raw_ingest_to_replay_p95`
- `provider_timeout_rate`
- `provider_rate_limited_rate`
- `same_trace_ai_duplicate_call_rate`
- `market_data_default_used_rate`
- `execution_blocked_by_gate_rate`

## Data Source Rules
- Baseline values must come from reproducible run logs.
- Any value without provenance is invalid for DoD.
- Freeze timestamp and commit SHA are mandatory.

## Freeze Metadata
- Freeze timestamp: 2026-04-21T19:29:51Z
- Commit SHA: a26c9b6a68a04c75f98081d507b92029541d59d7
- Run command: `python3 scripts/freeze_stage0_baseline.py`
- Review signatures:
  - A formal review approve: pending
  - B formal review approve: pending
  - C formal review approve: pending
- Go / No-Go record: `GO` (2026-04-22, Stage 0 content gate passed; merge gate still requires formal A/B/C approve closure)
