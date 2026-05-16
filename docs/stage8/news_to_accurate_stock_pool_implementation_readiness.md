# Stage 8-A Implementation Readiness Review

## 0. Document Status

- `doc_status`: current_planning_readiness_review
- `updated_at`: 2026-05-16
- Authority boundary: readiness review only; does not grant runtime authority.

## 1. Purpose

This document records the implementation readiness review for Stage 8-A News-to-Accurate-Stock-Pool Repair.

It is based on:

- `docs/stage8/news_to_accurate_stock_pool_plan.md`
- `docs/stage8/news_to_accurate_stock_pool_ownership.md`
- `docs/stage8/news_to_accurate_stock_pool_contract_matrix.md`
- `docs/stage8/news_to_accurate_stock_pool_phase0_interface_freeze.md`

Refs #134

This document is planning-only. It does not authorize runtime implementation.

## 2. Current Planning Artifacts

The Stage 8-A planning set is complete and in main:

- planning baseline
- ownership and responsibility model
- contract / config / test-gate matrix
- Phase 0 interface freeze

These artifacts establish the planning boundary before implementation begins.

## 3. Readiness Checklist

Readiness requires all of the following to remain true:

- planning baseline is merged
- ownership model is merged
- contract matrix is merged
- Phase 0 interface freeze is merged
- shadow-only / advisory-only boundary remains in force
- CI gate names are explicit
- required tests are explicit
- config source-of-truth is explicit
- feature flags are explicit
- no implementation PR may exceed the approved Stage 8-A scope

## 4. Stage8A-Impl-1 Candidate Scope

Stage8A-Impl-1 may only cover:

- Pipeline Order
- Conduction Split
- Semantic Prepass Contract

Stage8A-Impl-1 must remain the first implementation slice and may not expand beyond this boundary.

## 5. Stage8A-Impl-1 Non-Goals

Stage8A-Impl-1 must not implement:

- CandidateEnvelope implementation
- Entity Resolver implementation
- Semantic Full Peer Expansion implementation
- Market Validation implementation
- PathAdjudicator implementation
- OutputAdapter implementation
- Lifecycle/Fatigue implementation
- Direction / Cross-news / Crowding gates
- execution / broker / final_action behavior

## 6. Required Tests Before / During Impl-1

Stage8A-Impl-1 must be backed by deterministic tests and CI gates aligned to the contract matrix.

Required tests for the first slice:

- pipeline order coverage
- semantic prepass contract coverage

Test data and replay inputs must remain deterministic.

## 7. Required Feature Flags

At minimum, Stage 8-A implementation must preserve the shadow-only feature boundary:

- `enable_v5_shadow_output = true`
- `enable_replace_legacy_output = false`

Additional flags may exist later, but Stage8A-Impl-1 must not require production authority.

## 8. Required Config Policy

Required policy:

- thresholds must come from `configs/*.yaml`
- hardcoded business thresholds are forbidden
- missing config must fail closed or fail fast in production
- shadow / replay may degrade to observe_only

## 9. Required CI Gate Names

Implementation readiness requires CI gate names to be frozen by the contract matrix and recognized by workflow configuration.

The following names must be used exactly as declared in the contract matrix:

- `pipeline-order-contract`
- `candidate-envelope-contract`
- `resolver-merge-contract`
- `semantic-full-peer-contract`
- `market-validation-contract`
- `path-adjudicator-lite-contract`
- `semantic-verdict-contract`
- `output-adapter-contract`
- `gate-diagnostics-contract`
- `advisory-governance-contract`
- `threshold-config-contract`
- `ci-workflow-step-contract`

The retired compatibility gate remains removed until a real runtime surface and test exist:

- `compatibility-exit-contract` (retired / removed)

## 10. Shadow-Only / Advisory-Only Boundary

Required boundary:

```text
enable_v5_shadow_output = true
enable_replace_legacy_output = false
comparison_status = observe_only or shadow_validated
```

No implementation PR may claim production effect while this boundary is active.

## 11. Execution / Broker / final_action Boundary

Stage 8-A implementation readiness does not permit touching execution / broker / final_action behavior.

Any change that touches those surfaces is out of scope for Stage8A-Impl-1 and invalidates the readiness assumption for this review.

## 12. Known Risks

- scope creep from Pipeline Order into downstream candidate / market / adjudication logic
- silent expansion of the first implementation slice beyond semantic prepass and conduction split
- production authority being implied too early
- CI gates drifting away from the declared contract matrix
- non-deterministic fixtures undermining reviewability

## 13. Implementation Entry Verdict

Implementation Entry Verdict: READY WITH CONDITIONS

Conditions:

- Stage8A-Impl-1 only handles Pipeline Order + Conduction Split + Semantic Prepass Contract
- no final production authority is introduced
- `release_status` is not marked `valid`
- `enable_v5_shadow_output = true`
- `enable_replace_legacy_output = false`
- execution / broker / final_action are not modified
- new tests are added to CI
- CI step names are implemented exactly as declared in the contract matrix
- live market data is forbidden in CI gates
- missing config must not silently fallback to a valid result

## 14. Out of Scope

- runtime code
- schema
- config
- tests
- CI
- old docs
- docs/archive
- Stage 8-A implementation
- Market Confirmation Gate implementation
- exposure map implementation
- outcome attribution implementation
- semantic sector scorer implementation
- execution / broker / final_action changes

## 15. Acceptance Criteria

- planning artifacts are complete
- Stage8A-Impl-1 boundary is explicit
- non-goals are explicit
- required tests are explicit
- feature flags are explicit
- config policy is explicit
- CI gate names are explicit
- shadow-only and advisory-only boundaries are explicit
- readiness verdict is explicit and conditional
- the document can gate implementation without itself implementing anything
