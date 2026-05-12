# Stage 8-A Ownership and Responsibility Model

## 1. Purpose

This document freezes the Stage 8-A ownership model before any implementation begins.

It is based on the source document `v5执行版三人分工方案.md` and exists to keep the news-to-accurate-stock-pool repair work shadow-only until the planning artifacts are reviewed and accepted.

Refs #134

## 2. Role Model

Stage 8-A uses a three-person ownership model:

- Member A: architecture / main pipeline / adjudication owner
- Member B: candidate pool / resolver / market validation owner
- Member C: CI / config / rollback / compatibility owner

The roles are intentionally split so implementation PRs can remain small, reviewable, and non-overlapping.

## 3. Member A Responsibilities

Role:

`Architecture / main pipeline / adjudication owner`

Member A is responsible for:

- `PR-1`: Pipeline Order + Conduction Split + Semantic Prepass Contract
- `PR-6`: Routing Authority + PathAdjudicator Lite + Semantic Verdict Fix
- `PR-7`: Final Selection Gates + Output Adapter + Gate Diagnostics

Hard acceptance:

- `conduction_final_selection` is the only outlet for `final_recommended_stocks`
- `OutputAdapter` does not mutate `final_recommended_stocks`
- `semantic_valid + company_anchor` can override weak/fallback rule
- strong macro rule can preserve template precedence
- execution / broker / final_action remain untouched

## 4. Member B Responsibilities

Role:

`Candidate pool / resolver / market validation owner`

Member B is responsible for:

- `PR-2`: SourceRanker Metadata Propagation + Candidate Envelope Compatibility
- `PR-3`: Entity Resolver + Multi-source Merge
- `PR-5`: Market Validation Before Final Selection
- partial `PR-8`: Lifecycle/Fatigue + Direction + Cross-news + Crowding

Hard acceptance:

- `template_candidates`, `anchor_candidates`, and `peer_candidates` merge into `unified_candidate_pool`
- same ticker multi-source merge preserves `source`, `role`, `relation`, and `event_id`
- `ambiguous`, `not_found`, and `market_blocked` candidates do not enter final selection
- fully reacted peer is downgraded or rejected
- lagging peer can enter final_selection
- every rejected candidate has an enumerated `reject_reason`

## 5. Member C Responsibilities

Role:

`CI / config / rollback / compatibility owner`

Member C is responsible for:

- global CI
- config single source of truth
- rollback matrix
- feature flags
- compatibility exit
- release status downgrade
- old_vs_v5_shadow_diff

Hard acceptance:

- `tests/test_ci_workflow_steps.py` passes
- workflow contains all declared CI step names
- `tests/test_threshold_config.py` passes
- feature flags can independently disable risky modules
- rollback restores legacy output
- `output_adapter_mutation_rate > 0` triggers downgrade

## 6. Phase 0 Interface Freeze

Before implementation, freeze these interfaces:

1. `CandidateEnvelope` schema
2. `path_decision_log` schema
3. `final_recommended_stocks` schema
4. `OutputAdapter` immutability rule
5. feature flag names

No implementation PR may change these without a planning re-review.

## 7. Execution Phases

Phase 0:

- planning docs
- ownership freeze
- interface freeze

Phase 1:

- PR-1, PR-2, and PR-3

Phase 2:

- PR-5, PR-6, PR-7, and PR-8

Phase 2 only begins after the Phase 0 contracts and ownership rules are approved.

## 8. Ownership Decision Rights

- Member A owns main pipeline order and final adjudication decisions.
- Member B owns candidate pool merge rules, resolver behavior, and market validation readiness.
- Member C owns CI gates, config source-of-truth, rollback compatibility, and release status downgrade policy.

If a change touches more than one area, the owning member for the earliest pipeline stage has final technical call, and the other members provide review.

## 9. Review Rules

- Review ownership must match the touched scope.
- No one should review a PR they are solely responsible for writing without a second reviewer.
- No implementation PR may use shadow-only evidence as production evidence.
- No PR may claim completion of Stage 8-A without the Phase 0 freeze artifacts.

## 10. Shadow-Only Boundary

```
enable_v5_shadow_output = true
enable_replace_legacy_output = false
comparison_status = observe_only or shadow_validated
```

No PR may claim production effect during the shadow-only phase.

## 11. Non-Touch Boundaries

- runtime code
- schema
- config
- tests
- CI
- execution / broker / final_action
- Market Confirmation Gate implementation
- exposure map implementation
- outcome attribution implementation
- semantic sector scorer implementation

## 12. Acceptance Criteria

- A / B / C ownership is explicit and non-overlapping
- Phase 0 interfaces are frozen
- shadow-only boundary is explicit
- implementation PR split is explicit
- non-touch boundaries are explicit
- the planning baseline can be reviewed without starting implementation
