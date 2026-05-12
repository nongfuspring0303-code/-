# Stage 8-A Planning Baseline

## 1. Purpose

This document defines the planning baseline for Stage 8-A, whose mainline is the repair of the news-to-accurate-stock-pool chain.

Baseline candidate: 《新闻到准确股票池修复最终版 v5（封板执行版）》

This file is planning-only. It does not authorize implementation work.

## 2. Current Problem Statement

The current chain has structural issues:

- pipeline timing is misordered
- decision inputs are misaligned
- downstream consumption does not close the loop
- the system tends to push first and explain later

Stage 8-A exists to repair the chain so the output is accurate, gated, and advisory-only.

## 3. Target Pipeline

The Stage 8-A target pipeline is:

`news → semantic_prepass → entity_resolver → semantic_full_peer_expansion → candidate_envelope → market_validation → path_adjudication → conduction_final_selection → advisory-only final_recommended_stocks`

The planning objective is to make this ordering explicit before any implementation begins.

## 4. Planning Scope

Planning should cover:

- pipeline order and phase boundaries
- semantic prepass contract
- entity resolution and merge precedence
- candidate envelope shape
- market validation timing and authority
- path adjudication and final selection rules
- advisory-only output adapter
- CI / test gate matrix

## 5. Ownership Boundary Preview

The三人分工方案 is not an implementation instruction yet.

After this baseline is reviewed and accepted, a separate docs-only ownership PR should define:

- A / B / C responsibilities
- Phase 0 interface freeze
- shadow-only execution boundary
- handoff and review ownership rules

## 6. Out of Scope

This planning baseline does not:

- modify runtime code
- modify schema
- modify config
- modify tests
- modify CI
- modify execution / broker / final_action
- implement Market Confirmation Gate
- implement exposure map
- implement outcome attribution expansion
- implement semantic sector scorer
- start any implementation PR

## 7. Required Planning Artifacts

Stage 8-A planning should eventually produce:

- a contract / config / test-gate matrix
- a current-state mapping from the v5 baseline to repository reality
- a pipeline order specification
- a routing authority specification
- an advisory-only output specification

## 8. Stage Split

Planning phase:

1. Stage8A-Plan-1: add planning baseline doc
2. Stage8A-Plan-2: add contract/config/test-gate matrix

Implementation phase, only after planning approval:

1. Stage8A-Impl-1: Pipeline Order + Conduction Split + Semantic Prepass Contract
2. Stage8A-Impl-2: SourceRanker Metadata Propagation + Candidate Envelope
3. Stage8A-Impl-3: Entity Resolver + Multi-source Merge
4. Stage8A-Impl-4: LLM Peer Expansion + Semantic Full Stage
5. Stage8A-Impl-5: Market Validation Before Final Selection
6. Stage8A-Impl-6: Routing Authority + PathAdjudicator Lite + Semantic Verdict Fix
7. Stage8A-Impl-7: Final Selection Gates + Output Adapter + Gate Diagnostics
8. Stage8A-Impl-8: Lifecycle/Fatigue + Direction + Cross-news + Crowding

## 9. Gatekeeping Rule

No implementation PR may start until the planning baseline, contract matrix, and ownership boundaries are reviewed and approved.

## 10. Next Step

After this baseline merges, create the separate docs-only ownership file:

`docs/stage8/news_to_accurate_stock_pool_ownership.md`

That follow-up file should freeze A/B/C ownership, Phase 0 interfaces, and the shadow-only execution boundary.
