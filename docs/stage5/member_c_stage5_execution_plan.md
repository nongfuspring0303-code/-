# Member C Stage5 Execution Plan (Logs + Scorecard + Dashboard)

Date: 2026-04-24  
Owner: Member C  
Scope: Stage5 implementation ownership only; A/B sign-off remains required.

## 1) C-side task extraction from the 5 canonical task files

Source files:
- `/Users/workmac/.openclaw/workspace/阶段五项目任务/EDT_施工顺序表_v1.0.2_2026-04-21.md`
- `/Users/workmac/.openclaw/workspace/阶段五项目任务/EDT_施工准备清单_开工门禁_v1.0.2_2026-04-21.md`
- `/Users/workmac/.openclaw/workspace/阶段五项目任务/EDT_三成员分工表_联审触点_v1.0.2_2026-04-21.md`
- `/Users/workmac/.openclaw/workspace/阶段五项目任务/EDT_阶段-负责人矩阵_v1.0_2026-04-21.md`
- `/Users/workmac/.openclaw/workspace/阶段五项目任务/EDT_施工顺序表_施工准备清单_三成员分工表_正式冻结版_v1.0.2_2026-04-21 (1).md`

C-side implementation tasks:
1. stage log full coverage: `pipeline_stage.jsonl`
2. rejected/quarantine logs: `rejected_events.jsonl`, `quarantine_replay.jsonl`
3. scorecard log: `trace_scorecard.jsonl`
4. provider/system health outputs: `provider_health_hourly.json`, `system_health_daily.json`
5. evaluator tool: `system_log_evaluator.py`
6. dashboard/daily report output

## 2) Rules to Code/Test mapping (for PR review template v2.1 traceability)

| Rule ID | Rule statement | Code anchor | Test anchor |
| --- | --- | --- | --- |
| R-C-S5-001 | Must write full stage-log per trace. | `scripts/full_workflow_runner.py` (`pipeline_stage.jsonl`) | `tests/test_stage5_log_outputs.py::test_stage5_pipeline_stage_and_scorecard_written` |
| R-C-S5-002 | Non-execute path must produce rejected/quarantine evidence. | `scripts/full_workflow_runner.py` (`rejected_events.jsonl`, `quarantine_replay.jsonl`) | `tests/test_stage5_log_outputs.py::test_stage5_rejected_and_quarantine_written_for_non_execute` |
| R-C-S5-003 | Must write trace scorecard for A/B/C scoring dimensions. | `scripts/full_workflow_runner.py` (`trace_scorecard.jsonl`) | `tests/test_stage5_log_outputs.py::test_stage5_pipeline_stage_and_scorecard_written` |
| R-C-S5-004 | Must output provider health hourly from provenance logs. | `scripts/system_log_evaluator.py` (`provider_health_hourly.json`) | `tests/test_system_log_evaluator.py::test_system_log_evaluator_generates_provider_and_daily_health` |
| R-C-S5-005 | Must output system health daily + quarantine silent alert evaluation. | `scripts/system_log_evaluator.py` (`system_health_daily.json`) | `tests/test_system_log_evaluator.py::test_system_log_evaluator_generates_provider_and_daily_health` |
| R-C-S5-006 | Must output dashboard/daily report artifact. | `scripts/system_log_evaluator.py` (`system_health_daily_report.md`) | `tests/test_system_log_evaluator.py::test_system_log_evaluator_generates_provider_and_daily_health` |

## 3) Joint review touchpoint reminder

This PR only implements C-owned observability/evaluator paths.  
Any change involving contract fields, gate semantics, or sector/ticker interpretation remains A/B/C joint-review territory.
