# PR112 Scope (Execution Suggestion Only)

## Objective
Add analysis-layer execution suggestions for human review only, without any automatic execution coupling.

## In Scope
- `execution_suggestion` contract fields:
  - `trade_type`
  - `position_sizing`
  - `entry_timing`
  - `risk_switch`
  - `stop_condition`
  - `overnight_allowed`
- Schema and policy artifacts for suggestion fields
- Consumer boundary tests that enforce analysis-only usage

### Field Semantics (Core 6)
- `trade_type`: 交易类型建议（如 `low_buy` / `breakout` / `intraday_only` / `avoid` / `watch`）
- `position_sizing`: 建议仓位区间，仅用于人工复核，不得直接用于自动下单数量
- `entry_timing`: 入场时机或触发条件（原 `entry_condition` 作为子说明）
- `risk_switch`: 风险开关（如 `no_trade` / `reduce_only` / `kill_switch` / `normal`，`risk_level` 仅作辅助信息）
- `stop_condition`: 失效、止损或退出条件（原 `invalidation_condition` 作为子说明）
- `overnight_allowed`: 是否允许过夜（`true` / `false` / `conditional`）

## Hard Boundary
- Suggestions are **advisory only** and must not be consumed by:
  - `workflow_runner.py`
  - Gate decision logic
  - final action generation
  - broker/execution emit path
- Suggestions must not trigger automatic trading, order placement, or position execution.

## Out of Scope
- No auto-trading action changes
- No gate threshold changes
- No execution engine changes
- No runtime artifact commits (`logs/`, `reports/`)

## Acceptance Criteria
- Suggestion fields are present and schema-valid
- Explicit tests prove no execution-chain consumption
- CI includes PR112 contract tests
- Implementation PR must include:
  - `configs/execution_suggestion_policy.yaml`
  - `schemas/execution_suggestion.schema.json`
  - analysis-layer builder/mapper
  - `tests/test_execution_suggestion_schema.py`
  - `tests/test_execution_suggestion_policy_contract.py`
  - `tests/test_execution_suggestion_consumer_boundary.py`
