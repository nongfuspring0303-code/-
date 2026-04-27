# Stage6 PR-7 Taskbook: Outcome Attribution

## Goal

Implement Stage6 outcome attribution as a read-only evaluation layer with contract-first delivery.

## Scope

- PR-7a (Contract Freeze)
  - schemas:
    - `schemas/opportunity_outcome.schema.json`
    - `schemas/log_trust.schema.json`
    - `schemas/mapping_attribution.schema.json`
  - policy/config:
    - `configs/outcome_scoring_policy.yaml`
    - `configs/metric_dictionary.yaml` (Stage6 metrics section)
  - governance:
    - `module-registry.yaml` Stage6 module declaration
    - `docs/stage6/STAGE6_SCOPE_CANONICAL.md`
    - `docs/review/pr7_rules_test_mapping.md`
- PR-7b (Outcome Engine / Summary / Report)
  - engine + tests + fixtures
  - no runtime output artifact commit

## Acceptance Gate

1. Stage6 schemas load successfully.
2. Policy is the single threshold source.
3. Rule↔Test mapping exists and is complete.
4. Metric dictionary and output fields are mutually traceable.
5. Canonical scope exists and is cited in PR.

## Non-goals

- No gate/action semantic changes.
- No broker/live trading integration.
- No mutation of upstream Stage5 evidence schema.
