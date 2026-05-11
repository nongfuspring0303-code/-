# Obsolete Docs Map

## 1. Purpose

This document maps obsolete, superseded, and reference-only documents so Codex / AI does not treat old planning text as current source-of-truth.

Refs #125

## 2. Current Active Governance Anchors

Use these as the current governance anchors:

- `docs/AI_CONTEXT_INDEX.md`
- `docs/PROJECT_CURRENT_STATE.md`
- `docs/DOC_STATUS_INDEX.md`
- `docs/pr/pr1_frontend_visibility_evidence_pack.md`
- `docs/pr/pr2_project_gap_monitor_evidence_pack.md`
- `docs/pr/pr3_ui_polish_project_health_evidence_pack.md`
- `docs/system/project_gap_monitor_design.md`
- `docs/system/local_monitor_setup.md`

## 3. Obsolete / Superseded Categories

The following document types are typically obsolete or superseded unless an active governance anchor explicitly re-references them:

- closed 0-diff placeholder PR descriptions
- superseded stage planning docs
- old review notes that were superseded by merged Evidence Packs
- historical alignment notes that no longer match merged code or tests

## 4. Reference-Only Categories

Treat the following as reference-only unless re-promoted by an active document:

- older stage planning docs
- historical design sketches
- archived discussion notes
- legacy PR descriptions that were not merged as implementation truth
- background notes that explain why a path was chosen but do not define current behavior

## 5. Deprecated Categories

Treat the following as deprecated / superseded:

- PR89, which was closed, not merged, and used as a 0-diff placeholder
- superseded plans that conflict with merged code, tests, configs, or Evidence Packs
- stale review text that conflicts with the current source-of-truth anchors

Deprecated material should not override current behavior or governance.

## 6. Conflict Resolution Rule

If a historical document conflicts with current code, tests, configs, Evidence Packs, `docs/AI_CONTEXT_INDEX.md`, `docs/PROJECT_CURRENT_STATE.md`, or `docs/DOC_STATUS_INDEX.md`, the current implementation and active governance anchors take precedence.

Historical text never overrides merged behavior.

## 7. AI / Codex Handling Rule

Default reading order:

1. The current PR diff
2. `docs/AI_CONTEXT_INDEX.md`
3. `docs/PROJECT_CURRENT_STATE.md`
4. `docs/DOC_STATUS_INDEX.md`
5. The active Evidence Pack or current source-of-truth files touched by the task
6. Only then consult reference-only or deprecated history if the task explicitly requires it

Do not load all historical documents by default.

## 8. Not a Deletion List

This map is not a deletion authorization.

It does not authorize moving, deleting, or archiving files. It only helps classify document intent and current relevance.

## 9. Out of Scope

- Do not modify runtime, schema, config, tests, or CI in this PR.
- Do not move, delete, or archive old documents in this PR.
- Do not close Issue125 in this PR.
- Do not start Stage 8 implementation in this PR.
- Do not add Market Confirmation Gate, exposure map, outcome attribution expansion, or semantic sector scorer here.
- Do not change broker / execution / final_action behavior here.

## 10. Next Step

Future docs normalization remains tracked by Issue125.
Stage 8 may only enter planning after docs governance boundaries are explicit.
