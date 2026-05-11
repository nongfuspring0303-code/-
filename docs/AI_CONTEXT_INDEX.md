# AI Context Index

## 1. Current Project Status

Stage 7 status:

`Stage 7 Mainline Complete / Closure Validation PASS`

Stage 7 mainline PRs:

- PR115: Frontend Visibility / Trace Detail / read-only project APIs
- PR116: Project Gap Monitor / read-only gap discovery
- PR117: Project Health UI / daily monitor integration

Stage 7 cleanup status:

- PR89: closed, not merged. It was a 0-diff placeholder PR and should not be used as active context.
- Issue125: open. It is the backlog tracking hub for final documentation normalization.

Current policy:

Stage 7 is frozen for mainline feature work. New work must be routed into one of:

- Stage 7.5 Hardening
- Stage 8 Feature Work
- Docs Governance / Issue125

## 2. Default AI / Codex Reading Order

For future Codex / AI tasks, read in this order:

1. The current PR diff
2. This file: `docs/AI_CONTEXT_INDEX.md`
3. The relevant Evidence Pack for the active PR
4. The active source-of-truth contract / schema / config files touched by the task
5. The current PR review template
6. Only then read historical stage docs if the task explicitly requires them

Do not load all historical docs by default.

## 3. Current Source-of-Truth Documents

For Stage 7 Web Console / Project Health / Gap Monitor work, treat the following as the primary governance sources:

- `docs/pr/pr1_frontend_visibility_evidence_pack.md`
- `docs/pr/pr2_project_gap_monitor_evidence_pack.md`
- `docs/pr/pr3_ui_polish_project_health_evidence_pack.md`
- `docs/system/project_gap_monitor_design.md`
- `docs/system/local_monitor_setup.md`
- `PR正式审查模板_v2.2_强制门禁版.md` if available in local project context
- `frontend_field_matrix_v2_1.md` if available in local project context
- `Major Event Web Console 最终施工基线 v1.0.md` if available in local project context

If a historical document conflicts with current code, tests, schemas, configs, or merged PR evidence, prefer the current implementation and merged Evidence Pack.

## 4. Historical / Reference-Only Context

Older stage documents may contain useful background but must not override current merged behavior.

Historical docs should be treated as reference-only unless explicitly promoted in a current Evidence Pack or source-of-truth file.

Examples of reference-only material:

- older Stage 5 governance docs
- older Stage 6 planning docs
- old placeholder docs
- stale PR descriptions
- superseded review notes

Do not use historical docs to override:

- current schema
- current config
- current runtime code
- current tests
- merged Evidence Packs
- current PR review rules

## 5. Stage 7 Frozen Boundary

Allowed Stage 7 follow-up work:

- regression bug fixes
- final closure evidence
- security / artifact hygiene fixes
- small documentation corrections

Not allowed under Stage 7:

- new feature development
- Market Confirmation Gate
- complete exposure map
- complete outcome attribution expansion
- complete semantic sector scorer
- broker / final_action / execution behavior changes
- large documentation normalization

These belong to Stage 7.5, Stage 8, or Docs Governance.

## 6. Stage 7.5 Hardening Backlog

Stage 7.5 should contain small hardening tasks only, such as:

- runtime artifact hygiene
- monitor-script cleanup behavior
- tighter no-logs safeguards
- post-PR124 guard tightening if required
- additional regression tests for existing Stage 7 behavior

Stage 7.5 must not become a hidden Stage 8 feature bucket.

## 7. Stage 8 Feature Work

Stage 8 may include larger feature work such as:

- complete semantic sector scorer
- exposure map
- outcome attribution expansion
- Market Confirmation Gate
- advanced provider configuration
- advanced frontend UI expansion

Stage 8 work must be opened as separate scoped PRs with real diffs, tests, and Evidence Packs.

## 8. Docs Governance / Issue125

Issue125 is the backlog hub for final documentation normalization.

Do not close Issue125 in this PR.

Future docs governance should be split into small PRs:

1. Add / maintain `docs/AI_CONTEXT_INDEX.md`
2. Mark active / deprecated / reference-only docs
3. Add `docs/PROJECT_CURRENT_STATE.md`
4. Add `docs/obsolete_docs_map.md`
5. Add final acceptance summary only after the relevant validation is complete

Do not create 0-diff placeholder PRs.

## 9. PR Review Context Rules

For future PR review:

- Open PRs must have real diff.
- 0-diff placeholder PRs should not remain open.
- Docs-only PRs must not claim implementation completion.
- Implementation PRs must not include large opportunistic docs cleanup.
- Runtime artifacts under `logs/` must not be committed.
- Tests and Evidence Packs remain required for implementation changes.
