# Document Status Index

## 1. Purpose

This file classifies current project documents so Codex / AI can distinguish active governance sources from reference-only or deprecated material.

Refs #125

## 2. Status Categories

- `active`: current source-of-truth documents that should be read first for current governance or execution context.
- `reference-only`: historical or background documents that may help with context but must not override active sources.
- `deprecated`: superseded documents that should not be used for current decisions unless explicitly re-referenced by an active document.

## 3. Active Documents

- `docs/AI_CONTEXT_INDEX.md`
- `docs/PROJECT_CURRENT_STATE.md`
- `docs/pr/pr1_frontend_visibility_evidence_pack.md`
- `docs/pr/pr2_project_gap_monitor_evidence_pack.md`
- `docs/pr/pr3_ui_polish_project_health_evidence_pack.md`
- `docs/system/project_gap_monitor_design.md`
- `docs/system/local_monitor_setup.md`

## 4. Reference-Only Documents

- Older stage planning docs not explicitly promoted by `AI_CONTEXT_INDEX.md` or `PROJECT_CURRENT_STATE.md`
- Historical PR notes and archived evidence that provide background but do not define current behavior
- Legacy review notes that are helpful for context but are not part of the current source of truth

## 5. Deprecated / Superseded Documents

- 0-diff placeholder PR descriptions or tracking notes that were closed without real diff
- Any document explicitly superseded by a later active source-of-truth file

## 6. Conflict Resolution Rule

If a historical document conflicts with merged code, tests, configs, Evidence Packs, `docs/AI_CONTEXT_INDEX.md`, or `docs/PROJECT_CURRENT_STATE.md`, the current code, tests, configs, and active evidence take precedence.

Historical docs do not override merged behavior.

## 7. AI / Codex Reading Rule

Read in this order:

1. The current PR diff
2. `docs/AI_CONTEXT_INDEX.md`
3. `docs/PROJECT_CURRENT_STATE.md`
4. The active Evidence Pack or current source-of-truth files touched by the task
5. Only then consult reference-only history if the task explicitly needs it

Do not load all historical docs by default.

## 8. Out of Scope

- Do not modify runtime, schema, config, tests, or CI in this PR.
- Do not move, delete, or archive old documents in this PR.
- Do not close Issue125 in this PR.
- Do not start Stage 8 implementation in this PR.
- Do not add Market Confirmation Gate, exposure map, outcome attribution expansion, or semantic sector scorer here.
- Do not change broker / execution / final_action behavior here.

## 9. Next Step

Future docs normalization remains tracked by Issue125.
Stage 8 may only enter planning after docs governance boundaries are explicit.
