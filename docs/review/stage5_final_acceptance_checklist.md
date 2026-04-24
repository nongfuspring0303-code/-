# Stage5 Final Acceptance Checklist (Execution Version)
**Version**: v1.0  
**Date**: 2026-04-24  
**PR**: #91 (Draft)  
**Branch**: `final-acceptance/stage5-dod-closure`

## 1) Unified Evidence Backfill Rules

- Final acceptance primary evidence must be backfilled in this file.
- PR comments are summary-only and are not the source of truth.
- Each evidence item must include:
  - file/log/script path
  - test command
  - result summary
  - current conclusion

Evidence entry template:

| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| `<item>` | `<path>` | `<command>` | `<summary>` | `PASS / PASS WITH NOTE / FAIL` |

## 2) A-side Backfill Area

### 2.1 Gate/blocker/stale/default/fallback evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| Gate/blocker semantic evidence | `docs/stage5/member_a_stage5_gate_safety_signoff.md`; `tests/test_member_a_stage5_gate_safety_contract.py`; `tests/test_stage5_log_outputs.py` | `python3 -m pytest -q tests/test_member_a_stage5_gate_safety_contract.py tests/test_stage5_log_outputs.py tests/test_execution_workflow.py` | 2026-04-24 local rerun passed (`25 passed`), blocker visibility fields and score-cap behavior asserted. | PASS |
| stale/default/fallback blocking evidence | `tests/test_member_a_stage2_gates.py`; `scripts/full_workflow_runner.py` (`a_gate_blocker_codes`, `a_score_cap_applied`) | `python3 -m pytest -q tests/test_member_a_stage2_gates.py` | stale/default/fallback paths are blocked with explicit reason codes and evidence logs. | PASS |

### 2.2 dual-write backward compatibility evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| dual-write compatibility | `tests/test_member_c_stage4_provider_perf.py::test_dual_write_backward_compat_test`; `scripts/full_workflow_runner.py` | `python3 -m pytest -q tests/test_member_c_stage4_provider_perf.py::test_dual_write_backward_compat_test` | `contract_version=v2.2` + `legacy_contract_version=v1.0` + `dual_write=true` verified in execution input and contract meta. | PASS |

### 2.3 State-machine/execution-boundary evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| state-machine boundary | `tests/test_state_machine.py`; `tests/test_execution_workflow.py` | `python3 -m pytest -q tests/test_state_machine.py tests/test_execution_workflow.py` | 2026-04-24 local rerun passed (`42 passed` in combined A+boundary batch), no state-machine semantic regression observed. | PASS |
| execution boundary | `tests/test_execution_workflow.py`; `tests/test_member_a_stage2_gates.py` | `python3 -m pytest -q tests/test_execution_workflow.py tests/test_member_a_stage2_gates.py` | output gate and execution decision boundaries remain enforced under contract-required fields. | PASS |

### 2.4 A-side final sign-off
- Status: `PASS`
- Sign-off note: Aligned with `docs/stage5/member_a_stage5_gate_safety_signoff.md` (A-side sign-off PASS, 2026-04-24).
- Residual risk: Runtime-window DoD metrics still require final clean-window recomputation (see Section 9 gaps).

## 3) B-side Backfill Area

### 3.1 Sector/ticker/output/mapping acceptance evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| sector quality evidence | `docs/stage5/member_b_stage5_scoring_policy.md`; `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_non_whitelist_sector_score_fails` | `python3 -m pytest -q tests/test_member_b_stage5_scorecard_contract.py` | non-whitelist scenarios force quality/sign-off failure as expected. | PASS |
| ticker quality evidence | `docs/stage5/member_b_stage5_required_fields.md`; `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_ticker_truth_source_miss_fails` | `python3 -m pytest -q tests/test_member_b_stage5_scorecard_contract.py` | truth-source miss path blocks B sign-off-ready. | PASS |
| output quality evidence | `docs/stage5/member_b_stage5_rules_test_mapping.md`; `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_placeholder_leakage_threshold_enforced` | `python3 -m pytest -q tests/test_member_b_stage5_scorecard_contract.py` | placeholder leakage path blocks B sign-off-ready. | PASS |
| mapping acceptance evidence | `docs/stage5/member_b_stage5_signoff_conclusion.md`; `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_signoff_ready_requires_all_quality_conditions` | `python3 -m pytest -q tests/test_member_b_stage5_scorecard_contract.py` | mapping acceptance score contributes to `b_signoff_ready`; all-quality-pass condition enforced. | PASS WITH NOTE |

### 3.2 B-side final sign-off
- Status: `PASS WITH NOTE`
- Sign-off note: Mirrors `docs/stage5/member_b_stage5_signoff_conclusion.md` (B-side sign-off PASS WITH NOTE).
- Residual risk: B-side rate metrics in Section 6 currently come from low-sample local snapshot (`trace_scorecard.jsonl`, n=4) and need clean-window backfill.

## 4) C-side Backfill Area

### 4.1 Replay/join/orphan evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| replay integrity | `tests/test_member_c_stage3a_replay_join_integrity.py`; `logs/replay_write.jsonl` | `python3 -m pytest -q tests/test_member_c_stage3a_replay_join_integrity.py` | replay primary keys and write path assertions pass; replay records emitted. | PASS |
| join integrity | `tests/test_member_c_stage3b_joint_review_evidence.py`; `logs/replay_join_validation.jsonl` | `python3 -m pytest -q tests/test_member_c_stage3b_joint_review_evidence.py` | join evidence path and trace/event/request alignment assertions pass. | PASS |
| orphan replay | `logs/replay_join_validation.jsonl` | `python3 scripts/system_log_evaluator.py --logs-dir logs` | current local snapshot contains historical orphan rows; needs clean-window recomputation before final closure. | FAIL |

### 4.2 Provider/failover/queue/perf evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| provider health evidence | `scripts/system_log_evaluator.py`; `logs/provider_health_hourly.json`; `logs/system_health_daily.json` | `python3 scripts/system_log_evaluator.py --logs-dir logs` | provider/system health artifacts generated successfully (hours/day snapshots present). | PASS WITH NOTE |
| failover evidence | `tests/test_market_data_adapter.py::test_market_data_adapter_batch_cache_and_failover`; `scripts/market_data_adapter.py` | `python3 -m pytest -q tests/test_market_data_adapter.py` | adapter failover and cache behavior validated (`3 passed`). | PASS |
| queue/ingest order semantics | `tests/test_member_c_stage4_provider_perf.py::test_priority_queue_order_semantics_test`; `tests/test_realtime_news_monitor.py::test_run_once_queues_fresh_news_without_dropping` | `python3 -m pytest -q tests/test_member_c_stage4_provider_perf.py::test_priority_queue_order_semantics_test tests/test_realtime_news_monitor.py::test_run_once_queues_fresh_news_without_dropping` | high/mid/low priority order and pending queue drain semantics validated. | PASS |
| perf baseline comparison | `docs/stage5/artifacts/pr88_stage4_perf_benchmark.json`; `docs/stage5/artifacts/pr88_stage4_runtime_window_metrics.json` | `python3 scripts/bench_stage4_provider_perf.py --rounds 60 --symbols-per-round 40 --out docs/stage5/artifacts/pr88_stage4_perf_benchmark.json` | baseline p95=189.54ms, stage4 warm p95=9.04ms, throughput ~20.44x vs baseline. | PASS |

### 4.3 Quarantine/rollback/purge gate evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| quarantine evidence | `tests/test_system_log_evaluator.py::test_system_log_evaluator_quarantine_silent_alert_on_hourly_window`; `logs/system_health_daily.json` | `python3 -m pytest -q tests/test_system_log_evaluator.py` | quarantine-activity monitor alert path validated (`2 passed`). | PASS |
| rollback evidence | `scripts/rollback_sanitize_v22.py`; `tests/test_rollback_sanitize_v22.py` | `python3 -m pytest -q tests/test_rollback_sanitize_v22.py && python3 scripts/rollback_sanitize_v22.py --mode dry-run --db-action downgrade_v22_metadata` | rollback sanitizer dry-run/apply behavior and metadata downgrade contract validated. | PASS |
| purge gate evidence | `scripts/` + `tests/` grep scan (`print(...)` footprint) | `rg -n "\\bprint\\(" scripts tests` | current repository still has CLI/debug `print(...)` usage without dedicated allowlist gate. | FAIL |

### 4.4 C-side final sign-off
- Status: `PASS WITH NOTE`
- Sign-off note: C implementation scope is delivered per `docs/stage5/member_c_stage5_execution_plan.md`, with executable test anchors passing.
- Residual risk: `shadow_code_purge_gate` lacks dedicated enforced gate; orphan/latency/duplicate-rate still need final clean-window metric evidence.

## 5) Additional Gate Tests (4 items)

### 5.1 `provider_failover_recovery_test`
- Command: `python3 -m pytest -q tests/test_market_data_adapter.py::test_market_data_adapter_batch_cache_and_failover`
- Result: `1 passed`
- Evidence path: `tests/test_market_data_adapter.py`, `scripts/market_data_adapter.py`
- Conclusion: `PASS`

### 5.2 `quarantine_activity_monitor_test`
- Command: `python3 -m pytest -q tests/test_system_log_evaluator.py::test_system_log_evaluator_quarantine_silent_alert_on_hourly_window`
- Result: `1 passed`
- Evidence path: `tests/test_system_log_evaluator.py`, `scripts/system_log_evaluator.py`
- Conclusion: `PASS`

### 5.3 `rollback_sanitization_test`
- Command: `python3 -m pytest -q tests/test_rollback_sanitize_v22.py::test_rollback_sanitize_apply_downgrade_metadata && python3 scripts/rollback_sanitize_v22.py --mode dry-run --db-action downgrade_v22_metadata`
- Result: test passed + dry-run report generated successfully
- Evidence path: `tests/test_rollback_sanitize_v22.py`, `scripts/rollback_sanitize_v22.py`
- Conclusion: `PASS`

### 5.4 `shadow_code_purge_gate`
- Command: `rg -n "\\bprint\\(" scripts tests`
- Result: multiple hits found; no explicit Stage5 purge allowlist gate is enforced
- Evidence path: grep output snapshot; `scripts/*`, `tests/*`
- Conclusion: `FAIL` (requires dedicated purge gate automation)

## 6) DoD Metrics Backfill Area

| Metric | Target | Current Value | Evidence Path | Current Conclusion |
| --- | --- | --- | --- | --- |
| `missing_opportunity_but_execute_count` | `= 0` | `4` in current local `logs/decision_gate.jsonl` snapshot (legacy/historical rows mixed) | `logs/decision_gate.jsonl` (derived from local JSONL metric extraction) | FAIL (requires clean-window recomputation before sign-off) |
| `market_data_default_used_in_execute_count` | `= 0` | `0` in current local snapshot | `logs/decision_gate.jsonl`; `tests/test_member_a_stage2_gates.py` | PASS WITH NOTE (snapshot-based) |
| `sectors_non_whitelist_rate` | `= 0` | `0.0` from `trace_scorecard.jsonl` (`n=4`) | `logs/trace_scorecard.jsonl`; `tests/test_member_b_stage5_scorecard_contract.py` | PASS WITH NOTE (sample too small) |
| `placeholder_leak_rate` | `<= 1%` | `0.0` from `trace_scorecard.jsonl` (`n=4`) | `logs/trace_scorecard.jsonl`; `tests/test_member_b_stage5_scorecard_contract.py` | PASS WITH NOTE (sample too small) |
| `financial_rate` | `< 35%` | `0.0` from `trace_scorecard.jsonl` (`n=4`) | `logs/trace_scorecard.jsonl` | PASS WITH NOTE (sample too small) |
| `replay_primary_key_completeness` | `= 100%` | `0.0` in current local `replay_join_validation.jsonl` historical snapshot | `logs/replay_join_validation.jsonl`; `tests/test_member_c_stage3a_replay_join_integrity.py` | FAIL (must regenerate clean-window evidence) |
| `trace_join_success_rate` | `>= 99.0%` | `0.90` in current local historical snapshot | `logs/replay_join_validation.jsonl`; `tests/test_member_c_stage3b_joint_review_evidence.py` | FAIL (must regenerate clean-window evidence) |
| `orphan_replay` | `= 0` | `10` in current local historical snapshot | `logs/replay_join_validation.jsonl` | FAIL (must regenerate clean-window evidence) |
| `p95_decision_latency` vs baseline | `improved / justified` | `improved` (stage4 warm p95 `9.04ms` vs baseline `189.54ms`) | `docs/stage5/artifacts/pr88_stage4_perf_benchmark.json` | PASS |
| `same_trace_ai_duplicate_call_rate` vs baseline | `improved / justified` | Not backfilled by dedicated runtime metric script in PR91 | no frozen metric artifact yet | FAIL (needs explicit metric script + artifact) |

## 7) Draft -> Ready Conditions

- [x] DoD evidence is backfilled with explicit PASS/FAIL states
- [x] 4 additional gate-test results are backfilled
- [x] A/B/C final sign-offs are written in this file
- [ ] No unresolved blocker/major items remain

## 8) Ready -> Merge Conditions

- [ ] required checks are green
- [ ] formal approvals are completed
- [ ] no unresolved review conversations remain
- [ ] final acceptance conclusion is archived in this file

## 9) Open Gaps and Minimum Fix Actions

### Gap-1: Historical log pollution blocks DoD runtime metrics
- Symptom: local `logs/*.jsonl` mixes pre-acceptance/historical rows, causing false-negative metrics (`missing_opportunity_but_execute_count`, replay/join/orphan).
- Minimum action:
  1. run Stage5 acceptance in a clean log directory (`logs/stage5_acceptance_window/`)
  2. rerun metric extractor against clean window only
  3. backfill Section 6 with clean-window values + sample size

### Gap-2: `shadow_code_purge_gate` not formalized
- Symptom: only grep evidence exists; no enforceable allowlist/CI gate.
- Minimum action:
  1. add dedicated test/script gate (e.g. `tests/test_shadow_code_purge_gate.py`)
  2. define allowlist for CLI entry scripts
  3. make gate required in CI before final merge

### Gap-3: `same_trace_ai_duplicate_call_rate` metric missing
- Symptom: no frozen artifact/script currently writes this metric in PR91 acceptance package.
- Minimum action:
  1. add metric extraction script from trace/event logs
  2. output artifact under `docs/stage5/artifacts/`
  3. backfill Section 6 with baseline comparison and conclusion
