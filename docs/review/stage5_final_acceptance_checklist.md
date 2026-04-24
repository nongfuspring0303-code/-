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
| Gate/blocker semantic evidence |  |  |  |  |
| stale/default/fallback blocking evidence |  |  |  |  |

### 2.2 dual-write backward compatibility evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| dual-write compatibility |  |  |  |  |

### 2.3 State-machine/execution-boundary evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| state-machine boundary |  |  |  |  |
| execution boundary |  |  |  |  |

### 2.4 A-side final sign-off
- Status: `PASS / PASS WITH NOTE / FAIL`
- Sign-off note:
- Residual risk:

## 3) B-side Backfill Area

### 3.1 Sector/ticker/output/mapping acceptance evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| sector quality evidence |  |  |  |  |
| ticker quality evidence |  |  |  |  |
| output quality evidence |  |  |  |  |
| mapping acceptance evidence |  |  |  |  |

### 3.2 B-side final sign-off
- Status: `PASS / PASS WITH NOTE / FAIL`
- Sign-off note:
- Residual risk:

## 4) C-side Backfill Area

### 4.1 Replay/join/orphan evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| replay integrity |  |  |  |  |
| join integrity |  |  |  |  |
| orphan replay |  |  |  |  |

### 4.2 Provider/failover/queue/perf evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| provider health evidence |  |  |  |  |
| failover evidence |  |  |  |  |
| queue/ingest order semantics |  |  |  |  |
| perf baseline comparison |  |  |  |  |

### 4.3 Quarantine/rollback/purge gate evidence
| Item | File/Log/Script Path | Test Command | Result Summary | Current Conclusion |
| --- | --- | --- | --- | --- |
| quarantine evidence |  |  |  |  |
| rollback evidence |  |  |  |  |
| purge gate evidence |  |  |  |  |

### 4.4 C-side final sign-off
- Status: `PASS / PASS WITH NOTE / FAIL`
- Sign-off note:
- Residual risk:

## 5) Additional Gate Tests (4 items)

### 5.1 `provider_failover_recovery_test`
- Command:
- Result:
- Evidence path:
- Conclusion:

### 5.2 `quarantine_activity_monitor_test`
- Command:
- Result:
- Evidence path:
- Conclusion:

### 5.3 `rollback_sanitization_test`
- Command:
- Result:
- Evidence path:
- Conclusion:

### 5.4 `shadow_code_purge_gate`
- Command:
- Result:
- Evidence path:
- Conclusion:

## 6) DoD Metrics Backfill Area

| Metric | Target | Current Value | Evidence Path | Current Conclusion |
| --- | --- | --- | --- | --- |
| `missing_opportunity_but_execute_count` | `= 0` |  |  |  |
| `market_data_default_used_in_execute_count` | `= 0` |  |  |  |
| `sectors_non_whitelist_rate` | `= 0` |  |  |  |
| `placeholder_leak_rate` | `<= 1%` |  |  |  |
| `financial_rate` | `< 35%` |  |  |  |
| `replay_primary_key_completeness` | `= 100%` |  |  |  |
| `trace_join_success_rate` | `>= 99.0%` |  |  |  |
| `orphan_replay` | `= 0` |  |  |  |
| `p95_decision_latency` vs baseline | `improved / justified` |  |  |  |
| `same_trace_ai_duplicate_call_rate` vs baseline | `improved / justified` |  |  |  |

## 7) Draft -> Ready Conditions

- [ ] DoD evidence is fully backfilled
- [ ] 4 additional gate-test results are fully backfilled
- [ ] A/B/C final sign-offs are all written in this file
- [ ] No unresolved blocker/major items remain

## 8) Ready -> Merge Conditions

- [ ] required checks are green
- [ ] formal approvals are completed
- [ ] no unresolved review conversations remain
- [ ] final acceptance conclusion is archived in this file

