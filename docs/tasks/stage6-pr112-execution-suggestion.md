# Stage6 PR112 Taskbook

## PR
PR112 - execution_suggestion only (human review assist)

## Owner / Reviewer
- Owner: C (implementation)
- Reviewer: A/B (contract + boundary review)

## Deliverables
1. Suggestion contract fields:
   - `trade_type`
   - `position_sizing`
   - `entry_timing`
   - `risk_switch`
   - `stop_condition`
   - `overnight_allowed`
2. Suggestion schema + policy files
3. Rule↔Test mapping for PR112
4. Boundary tests proving no execution-chain consumption

### Field Semantics (Core 6)
- `trade_type`: 交易类型建议（如 `low_buy` / `breakout` / `intraday_only` / `avoid` / `watch`）
- `position_sizing`: 建议仓位区间，仅用于人工复核，不得直接驱动自动下单数量
- `entry_timing`: 入场时机或触发条件（原 `entry_condition` 作为子说明）
- `risk_switch`: 风险开关（如 `no_trade` / `reduce_only` / `kill_switch` / `normal`，`risk_level` 仅作辅助信息）
- `stop_condition`: 失效、止损或退出条件（原 `invalidation_condition` 作为子说明）
- `overnight_allowed`: 是否允许过夜（`true` / `false` / `conditional`）

## Non-Negotiable Rules
- No automatic execution behavior from suggestion fields
- No Gate/final_action coupling
- No runtime artifact commits
- Suggestions must remain analysis-layer only and human-review only.
- `workflow_runner.py` / Gate / final_action / broker / execution path must not consume `execution_suggestion`.

## Suggested Test Anchors
- `test_execution_suggestion_schema.py`
- `test_execution_suggestion_consumer_boundary.py`
- `test_execution_suggestion_policy_contract.py`

## Exit Criteria
- Contract fields + schema + policy aligned
- CI test step green
- A/B formal review confirms advisory-only boundary
- Implementation PR must include:
  - `configs/execution_suggestion_policy.yaml`
  - `schemas/execution_suggestion.schema.json`
  - analysis-layer builder/mapper
  - `tests/test_execution_suggestion_schema.py`
  - `tests/test_execution_suggestion_policy_contract.py`
  - `tests/test_execution_suggestion_consumer_boundary.py`
