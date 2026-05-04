# PR112 Scope (Execution Suggestion Only)

## Objective
Add analysis-layer execution suggestions for human review only, without any automatic execution coupling.

## In Scope
- `execution_suggestion` contract fields:
  - `trade_type`
  - `entry_condition`
  - `risk_level`
  - `overnight_allowed`
  - `invalidation_condition`
- Schema and policy artifacts for suggestion fields
- Consumer boundary tests that enforce analysis-only usage

## Hard Boundary
- Suggestions are **advisory only** and must not be consumed by:
  - `workflow_runner.py`
  - Gate decision logic
  - final action generation
  - broker/execution emit path

## Out of Scope
- No auto-trading action changes
- No gate threshold changes
- No execution engine changes
- No runtime artifact commits (`logs/`, `reports/`)

## Acceptance Criteria
- Suggestion fields are present and schema-valid
- Explicit tests prove no execution-chain consumption
- CI includes PR112 contract tests
