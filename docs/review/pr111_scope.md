# PR111 Scope

PR111 仅实现并验证以下原子契约字段，不修改执行链路：

- `lifecycle_state`
- `fatigue_score`
- `time_scale`
- `decay_profile`
- `stale_event`

## In Scope

- `scripts/lifecycle_manager.py`：新增 `time_scale`、`decay_profile`、policy-driven `stale_event` downgrade 输出，并保证 `downgrade_applied=true` 时 `lifecycle_state == stale_event.downgrade_to`
- `scripts/fatigue_calculator.py`：新增 `fatigue_score`（别名）与 `fatigue_bucket`
- `scripts/full_workflow_runner.py`：新增分析层 `lifecycle_fatigue_contract` 聚合视图
- `configs/lifecycle_fatigue_contract_policy.yaml`：PR111 策略真源
- `schemas/lifecycle_fatigue_contract.schema.json`：PR111 契约 schema
- `tests/test_pr111_lifecycle_fatigue_contract.py`：契约与输出闭环测试，覆盖 `Active -> Exhaustion`、`Continuation -> Exhaustion`、`Detected -> Dead`、policy threshold override
- `.github/workflows/ci.yml`：加入 PR111 测试步骤

## Out of Scope

- 不修改 `workflow_runner.py`、Gate、execution、final_action
- 不引入自动交易逻辑
- 不提交运行时产物（`logs/`、`reports/`）
