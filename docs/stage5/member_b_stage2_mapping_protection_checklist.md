# Member B Stage2 Mapping Protection Checklist
**Version**: v1.0  
**Date**: 2026-04-22  
**Role**: Member B review / sign-off for Stage2 mapping protection  
**Scope**: Stage2 output-gate hardening only. This checklist covers B-side non-regression concerns when blocker logic is tightened.

---

## 1) What B must confirm

- `A1` is not turned into a dirty value, empty value, or semantic drift because a blocker was added.
- `target_tracking` is not cleared by unrelated blocker fixes.
- `semantic_event_type / sector_candidates / ticker_candidates / a1_score / theme_tags / tradeable / opportunity_count`
  remain available to B for replay review and mapping acceptance when a blocker fires.
- After a blocker fires, B must still be able to tell whether the event had no opportunity or had an opportunity but was blocked by `market_data_stale / market_data_default_used / market_data_fallback_used`.

---

## 2) Current repository-visible contract note

- The runtime code path in this repository currently exposes `A1` and the mapping summary fields above.
- A direct runtime consumer named `target_tracking` is not visible in the execution code path.
- Where `target_tracking` appears in the repo, it is currently a review / acceptance concept in docs and fixture labels, not a standalone execution-layer field.

---

## 3) B-side review checks

- Blocker-triggered outputs still carry `decision_gate.jsonl` summary fields.
- `final_reason` or blocker reason remains readable after `WATCH / BLOCK`.
- Mapping summary fields stay stable across:
  - complete market data
  - stale market data
  - default-used market data
  - fallback-used market data
- `has_opportunity=false` is distinguishable from `has_opportunity=true` plus a market-data blocker.

---

## 4) B sign-off condition

B may sign off Stage2 only when all of the following are true:

- The blocker hardening does not erase or mutate the B-side mapping summary.
- `A1` remains readable and semantically consistent.
- `target_tracking` is not unintentionally cleared where it already exists in the contract surface.
- B can decide whether the event is:
  - no opportunity, or
  - opportunity present but blocked for provenance / freshness reasons.
- The mapping chain remains reviewable from raw ingest through decision gate output.

