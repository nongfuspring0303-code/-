# Stage 8-A Contract / Config / Test-Gate Matrix

## 1. Purpose

This document freezes the contract, config, CI, and test-gate matrix for Stage 8-A planning.

It is planning-only and does not authorize implementation work.

It is based on `/Users/jia/Downloads/v5执行版三人分工方案.md`.

Refs #134

## 2. Contract Freeze Targets

Implementation cannot begin until these contracts are frozen:

- `CandidateEnvelope`
- `path_decision_log`
- `final_recommended_stocks`
- `RecommendationOutputAdapter` immutability
- `reject_reason` enum
- `downgrade_reason` enum
- `gate_diagnostics`
- source metadata propagation
- market_validation output
- release_status output

## 3. Config Single Source of Truth

All thresholds must come from `configs/*.yaml`.

Hardcoded business thresholds are forbidden.

Missing config must fail-fast in production.
Shadow / replay may degrade to `observe_only`.

Config groups:

- semantic thresholds
- resolver thresholds
- source ranker multipliers
- market validation thresholds
- lifecycle/fatigue thresholds
- crowding thresholds
- cross-news thresholds
- release status downgrade thresholds
- compatibility exit thresholds

## 4. PR-to-CI Test Binding

| PR | Required tests | CI step name | Pass condition |
| -- | -------------- | ------------ | -------------- |
| PR-1 | `tests/test_pipeline_order.py`, `tests/test_semantic_prepass_contract.py` | `pipeline-order-contract` | pipeline order and semantic prepass contract are deterministic and frozen |
| PR-2 | `tests/test_candidate_envelope.py`, `tests/test_source_metadata_propagation.py` | `candidate-envelope-contract` | candidate envelope fields and source metadata propagation are stable |
| PR-3 | `tests/test_entity_resolver.py`, `tests/test_candidate_merge.py` | `resolver-merge-contract` | entity resolution and multi-source merge preserve identity and reject invalid merges |
| PR-5 | `tests/test_market_validation.py` | `market-validation-contract` | market validation gates before final selection and blocks invalid candidates |
| PR-6 | `tests/test_path_adjudicator.py`, `tests/test_semantic_override.py`, `tests/test_semantic_verdict.py` | `routing-authority-contract` | routing authority and semantic verdict handling are stable |
| PR-7 | `tests/test_output_adapter.py`, `tests/test_gate_diagnostics.py` | `output-adapter-contract` | output adapter remains advisory-only and diagnostics are emitted consistently |
| PR-8 | `tests/test_lifecycle_fatigue_gate.py`, `tests/test_cross_news_conflict.py`, `tests/test_crowding_discount.py` | `advanced-gates-contract` | advanced gates are deterministic and do not leak into earlier phases |
| Global | `tests/test_threshold_config.py` | `threshold-config-contract` | thresholds are sourced from config and missing config fails safely |
| Global | `tests/test_compatibility_exit.py` | `compatibility-exit-contract` | rollback / compatibility exit behavior is deterministic |
| Global | `tests/test_ci_workflow_steps.py` | `ci-workflow-step-contract` | declared workflow step names exist exactly as specified |

## 5. Feature Flags

Required flags:

- `enable_v5_shadow_output`
- `enable_replace_legacy_output`
- `enable_conduction_split`
- `enable_source_metadata_propagation`
- `enable_semantic_prepass`
- `enable_semantic_full_peer_expansion`
- `enable_candidate_envelope`
- `enable_entity_resolver`
- `enable_candidate_merge`
- `enable_market_validation_gate`
- `enable_path_adjudicator_lite`
- `enable_semantic_verdict_fix`
- `enable_output_adapter_v4`
- `enable_gate_diagnostics`
- `enable_lifecycle_fatigue_gate`
- `enable_direction_gate`
- `enable_cross_news_conflict`
- `enable_crowding_discount`

## 6. Rollback Matrix

Each implementation PR must define a rollback object and a fallback rule.

- `PR-1`
  - rollback object: pipeline order and semantic prepass contract revert
  - fallback rule: return to shadow-only baseline with legacy ordering
- `PR-2`
  - rollback object: candidate envelope / source metadata revert
  - fallback rule: preserve legacy candidate selection without new envelope fields
- `PR-3`
  - rollback object: resolver merge disable
  - fallback rule: keep source-specific candidates separate and mark ambiguous merges rejected
- `PR-5`
  - rollback object: market validation gate disable
  - fallback rule: advisory-only observe path with explicit block reasons preserved
- `PR-6`
  - rollback object: routing authority / adjudicator revert
  - fallback rule: preserve previous verdict path and downgrade to observe_only
- `PR-7`
  - rollback object: output adapter and diagnostics revert
  - fallback rule: emit legacy output without mutating final recommendations
- `PR-8`
  - rollback object: lifecycle / fatigue / crowding gates disable
  - fallback rule: retain prior gate state and suppress new advanced-gate output

## 7. Metrics and Release Status

Legal release status states:

- invalid
- observe_only
- shadow_validated
- conditionally_authoritative
- valid

Stage 8-A target is at most `conditionally_authoritative`.

Do not mark `valid` in the first implementation round.

`output_adapter_mutation_rate > 0` triggers downgrade.

`wrong_market_rate` or `false_accept_rate` above threshold triggers downgrade.

Execution / broker / final_action touched = `invalid`.

## 8. Shadow / Advisory-Only Rules

```
enable_v5_shadow_output = true
enable_replace_legacy_output = false
comparison_status = observe_only or shadow_validated
```

No implementation PR may claim production effect while shadow-only is enabled.

## 9. Deterministic CI Rule

CI / contract tests must use deterministic fixtures or replay snapshots.

Live market data is forbidden in CI gates.

## 10. Implementation Entry Criteria

Implementation may begin only after:

- PR135 planning baseline merged
- ownership doc merged
- contract matrix merged
- Phase 0 interfaces frozen
- CI gate names accepted
- feature flags accepted
- shadow-only boundary accepted

## 11. Out of Scope

- runtime code
- schema
- config
- tests
- CI
- old docs
- docs/archive
- Issue134
- execution / broker / final_action
- Stage 8-A implementation
- Market Confirmation Gate implementation
- exposure map implementation
- outcome attribution implementation
- semantic sector scorer implementation

## 12. Acceptance Criteria

- contract freeze targets are explicit
- config source-of-truth is explicit
- PR-to-CI binding is explicit
- feature flags are explicit
- rollback matrix is explicit
- shadow/advisory-only rules are explicit
- deterministic CI is explicit
- implementation entry criteria are explicit
