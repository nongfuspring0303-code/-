# Stage 8-A Phase 0 Interface Freeze

## 1. Purpose

This document freezes the Phase 0 interface boundaries for Stage 8-A News-to-Accurate-Stock-Pool Repair.

It is based on:

- `docs/stage8/news_to_accurate_stock_pool_plan.md`
- `docs/stage8/news_to_accurate_stock_pool_ownership.md`
- `docs/stage8/news_to_accurate_stock_pool_contract_matrix.md`

Refs #134

This document defines contracts, immutable rules, failure behavior, and review gates only. It does not authorize runtime implementation.

## 2. Phase 0 Freeze Scope

Phase 0 freezes the interfaces that must not change before implementation begins:

- `CandidateEnvelope`
- `path_decision_log`
- `final_recommended_stocks`
- `RecommendationOutputAdapter` immutability
- `reject_reason` enum
- `downgrade_reason` enum
- `gate_diagnostics`
- source metadata propagation
- `market_validation` output contract
- `release_status` output contract

## 3. CandidateEnvelope Interface

`CandidateEnvelope` must be treated as the frozen carrier for candidate identity, source metadata, relation evidence, and routing context.

Required properties:

- stable candidate identity
- stable ticker identity
- source and role provenance
- relation evidence required for peer-derived candidates
- event linkage metadata
- deterministic ordering semantics for review and replay

Failure behavior:

- missing critical fields must not silently produce a valid candidate
- unknown or partial candidates must remain explicitly non-final until resolved
- a candidate without required provenance must be rejected or downgraded with a reason

## 4. path_decision_log Interface

`path_decision_log` must remain a deterministic audit trail for how a candidate moves through the Stage 8-A pipeline.

Required properties:

- ordered path records
- explicit decision stage names
- explicit accept / reject / downgrade reasons
- source metadata references where relevant
- final selection traceability

Failure behavior:

- malformed log entries must be rejected, not normalized into valid output
- absent path data must not be treated as proof of approval

## 5. final_recommended_stocks Interface

`final_recommended_stocks` is the advisory output surface.

Required properties:

- stable ticker identity
- advisory-only recommendation records
- required supporting provenance where applicable
- explicit gating outcome visibility

Rules:

- `conduction_final_selection` is the only allowed stage that may output `final_recommended_stocks`
- missing required fields must not be silently promoted into final recommendations
- unknown / missing / invalid values must not be disguised as valid recommendations

## 6. RecommendationOutputAdapter Immutability Rule

`RecommendationOutputAdapter` is format-compatible only.

It may:

- adapt representation
- preserve legacy-compatible layout where needed
- emit advisory-only records

It may not:

- add tickers
- delete tickers
- reorder tickers
- modify tickers
- mutate recommendation meaning

Any touch to execution / broker / final_action behavior is invalid for Phase 0.

## 7. reject_reason Enum

Every rejection must carry an enumerated `reject_reason`.

The enum must cover at least:

- missing required fields
- invalid source metadata
- ambiguous candidate origin
- market validation failure
- routing authority rejection
- shadow-only / non-final status

Rules:

- rejection without reason is invalid
- free-text-only rejection is insufficient
- enum values must be deterministic and reviewable

## 8. downgrade_reason Enum

Every downgrade must carry an enumerated `downgrade_reason`.

The enum must cover at least:

- weak source confidence
- partial provenance
- market validation weakness
- shadow-only behavior
- adapter compatibility downgrade
- release status downgrade

Rules:

- downgrade without reason is invalid
- downgrade must not silently become final approval

## 9. gate_diagnostics Interface

`gate_diagnostics` must expose the minimum information needed for review and rollback analysis.

Required properties:

- gate name
- gate status
- reason or rationale code
- deterministic pass / warn / fail classification
- rollback visibility for gated failures

## 10. Source Metadata Propagation Contract

Source metadata must propagate from candidate creation through merge, validation, adjudication, and output.

Required metadata includes:

- source
- role
- relation
- event_id

Rules:

- missing source metadata must not be converted into a valid merged candidate
- source metadata must remain consistent across the chain
- same-ticker multi-source merging must preserve provenance

## 11. market_validation Output Contract

`market_validation` must complete before final selection.

Required properties:

- deterministic validation result
- explicit block or allow outcome
- reason when blocked
- no dependency on live market data in CI gates

Rules:

- market validation after final selection is invalid
- missing validation output must not be treated as allow

## 12. release_status Output Contract

Release status must remain explicit and reviewable.

Legal states:

- invalid
- observe_only
- shadow_validated
- conditionally_authoritative
- valid

Rules:

- Stage 8-A target is at most `conditionally_authoritative`
- the first implementation round must not claim `valid`
- `output_adapter_mutation_rate > 0` triggers downgrade
- touching execution / broker / final_action makes the release status `invalid`

## 13. Failure / Missing / Invalid Input Behavior

General rules:

- missing critical fields must fail closed
- invalid payloads must be rejected or downgraded with a reason
- unknown values must not be rewritten as valid values
- fallback must preserve safety, not authority

Specific rules:

- no silent fallback from incomplete `CandidateEnvelope` to valid final candidate
- no silent fallback from malformed `path_decision_log` to approved state
- no silent fallback from invalid `release_status` to `valid`

## 14. Producer → Consumer Ownership

Ownership follows the pipeline:

- producers own the correctness of the data they emit
- consumers may validate, downgrade, or reject
- consumers may not invent missing meaning

At Phase 0, the ownership chain must be reviewable from candidate production to final advisory output.

## 15. Implementation Entry Blockers

Implementation may not begin until all of the following are accepted:

- planning baseline merged
- ownership doc merged
- contract matrix merged
- Phase 0 interfaces frozen
- CI gate names accepted
- feature flags accepted
- shadow-only boundary accepted
- contract review checklist accepted

## 16. Contract Review Checklist

Before implementation begins, reviewers must confirm:

- `CandidateEnvelope` is frozen
- `path_decision_log` is frozen
- `final_recommended_stocks` is frozen
- `RecommendationOutputAdapter` is immutable except for compatibility formatting
- every reject path has `reject_reason`
- every downgrade path has `downgrade_reason`
- `gate_diagnostics` is explicit
- source metadata propagation is stable
- `market_validation` happens before final selection
- CI uses deterministic fixtures or replay snapshots
- live market data is excluded from CI gates
- Stage 8-A release status cannot exceed `conditionally_authoritative`
- execution / broker / final_action touches are invalid

## 17. Out of Scope

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

## 18. Acceptance Criteria

- Phase 0 interfaces are frozen
- output authority is explicit
- failure behavior is fail-closed
- reject and downgrade reasons are explicit
- source metadata propagation is reviewable
- market validation ordering is explicit
- deterministic CI rules are explicit
- implementation entry blockers are explicit
- shadow-only and advisory-only boundaries remain intact
- the document can be used as a review gate without starting implementation
