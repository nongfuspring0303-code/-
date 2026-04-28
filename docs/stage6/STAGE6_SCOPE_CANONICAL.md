# STAGE6 Scope Canonical

Status: Final
Scope: Stage6 PR-7 (Outcome Attribution)

## In Scope

- Read-only consumption of Stage5/PR94 runtime evidence.
- Build outcome attribution records and summary/report outputs under `reports/outcome/`.
- Produce decision suggestions for human review only.
- Validate data quality, mapping attribution, score monotonicity, and outcome coverage.

## Out of Scope

- Any modification to `workflow_runner.py`, gate rules, final_action semantics, or execution path.
- Broker/live execution, portfolio PnL, kill-switch, full PIT engine, or automatic parameter tuning.
- Writing back into Stage5 evidence schemas or mutating upstream logs.

## Hard Constraints

- No fabricated market/provider/benchmark fields.
- Invalid/pending records must never be counted as resolved valid outcomes.
- Runtime output artifacts are not committed to git by default.
- `decision_suggestions.json` must not be auto-consumed by production execution modules.

## action_after_gate audit-only values

Stage6 `opportunity_outcome.schema.json` allows the following `action_after_gate` values:

- EXECUTE
- WATCH
- BLOCK
- PENDING_CONFIRM
- UNKNOWN

`PENDING_CONFIRM` and `UNKNOWN` are audit-only values.

Rules:

- They are allowed only so abnormal or immature upstream decisions can be represented in Stage6 audit outputs.
- They must not enter primary stats.
- They must not emit `hit` / `miss`.
- They must not enter alpha primary statistics.
- They must not enter score monotonicity primary statistics.
- They must be marked `data_quality=degraded` or `data_quality=invalid` according to policy.
- They must not change Gate behavior, execution behavior, or `final_action` semantics.

## PR Freeze Gate

Before PR-7a contract freeze:

1. Stage6 schemas exist and load.
2. `configs/outcome_scoring_policy.yaml` exists and is the single threshold source.
3. `configs/metric_dictionary.yaml` contains Stage6 metrics and formulas.
4. `module-registry.yaml` declares Stage6 module and schema/config links.
5. `docs/tasks/stage6-pr7-outcome-attribution.md` exists.
6. `docs/review/pr7_rules_test_mapping.md` exists.
