# Project Current State

## 0. Document Status

- `doc_status`: current_state_authoritative
- `updated_at`: 2026-05-16
- Scope: this file is the current-state index for merged audit status and maintainer boundaries.
- Non-authority: this file does not change runtime decision authority and does not authorize execution / broker / final_action changes.

## 1. Current Status

Stage 7 status:

`Stage 7 Mainline Complete / Closure Validation PASS / Context Index Added`

Stage 7.5 status:

`Stage 7.5 Hardening Complete`

Current routing:

- Docs Governance and current-state cleanup
- Stage 8 planning artifacts are merged and frozen as planning-only references
- Stage 8 implementation remains gated by explicit scope and CI contracts

## 2. Audit Wave Status (Issue #161)

- `PR-Audit-1` merged: runtime safety hotfix.
- `PR-Audit-2` merged: support scripts stability.
- `PR-Audit-3` merged: conduction mapper correctness.
- `PR-Audit-4` merged: CI contract cleanup.
- `PR-Audit-5A/5B` merged: test credibility repairs and CI binding.
- `PR-Audit-6` merged: config single source and consistency contracts.

## 3. Completed Stage 7 Mainline

- PR115, PR116, and PR117 were merged as the Stage 7 mainline.
- PR89 was closed and not merged as a 0-diff placeholder PR.
- PR124 was merged as the debroadcasting / ticker guard hardening layer.
- PR126 added `docs/AI_CONTEXT_INDEX.md`.
- Stage 7 closure validation passed.

## 4. Completed Stage 7.5 Hardening

- PR128 completed runtime artifact hygiene.
- PR129 completed no-logs / sensitive leak safeguards.
- PR7.5-3 passed preflight and did not require an implementation PR.
- PR7.5-4 passed preflight and did not require an implementation PR.

## 5. Active Governance Issues

- Issue #161 is the authoritative tracking hub for the current audit stabilization window and its review boundaries.
- Future PR-Audit-8..14 windows must be unlocked explicitly before execution.
- Issue125 remains open as the docs governance backlog hub.
- Issue127 is closed as completed after Stage 7.5 hardening closure.

## 6. Current Source-of-Truth Files

For current reading order and project state, use:

- `docs/AI_CONTEXT_INDEX.md`
- `docs/PROJECT_CURRENT_STATE.md`
- `docs/stage8/news_to_accurate_stock_pool_plan.md`
- `docs/stage8/news_to_accurate_stock_pool_ownership.md`
- `docs/stage8/news_to_accurate_stock_pool_contract_matrix.md`
- `docs/stage8/news_to_accurate_stock_pool_phase0_interface_freeze.md`
- `docs/stage8/news_to_accurate_stock_pool_implementation_readiness.md`
- `docs/pr/pr1_frontend_visibility_evidence_pack.md`
- `docs/pr/pr2_project_gap_monitor_evidence_pack.md`
- `docs/pr/pr3_ui_polish_project_health_evidence_pack.md`
- `docs/system/project_gap_monitor_design.md`
- `docs/system/local_monitor_setup.md`

If a historical doc conflicts with merged code, tests, configs, or Evidence Packs, prefer the current implementation and the merged evidence.

## 7. What Is Frozen

- Stage 7 mainline feature work is frozen.
- Stage 7.5 hardening is complete and frozen.
- Stage 8 planning docs are frozen as planning contracts, not runtime authority.
- 0-diff placeholder PRs are not an acceptable tracking mechanism.
- Runtime artifacts under `logs/` must not be committed.

## 8. What Is Allowed Next

- Docs governance and audit documentation work tracked by Issue125 and Issue #161.
- Stage 8 implementation only after planning scope, CI contracts, and ownership boundaries are explicit.
- Maintainers may update runbook/changelog/current-state docs without touching runtime authority surfaces.

## 9. What Is Not Allowed Next

- Do not begin Stage 8 implementation from this file alone.
- Do not add Market Confirmation Gate here.
- Do not add exposure map here.
- Do not add outcome attribution expansion here.
- Do not add semantic sector scorer here.
- Do not change broker / execution / final_action here.
- Do not modify runtime, schema, config, tests, or CI here.
- Do not move, delete, or archive old docs here.
- Do not close Issue125 or Issue127 here.

## 10. Project-Health / Gap-Monitor Boundary

- `scripts/project_gap_monitor.py` is read-only diagnostics and cannot mutate runtime logic.
- `logs/project_gap_report.*` and `logs/project_gap_state.json` are runtime artifacts and must stay out of git.
- Monitor outputs support maintenance triage only; they are not trading authority and not release authority.
- Any proposal that escalates monitor output into execution decisions is out of scope for docs-only work.

## 11. Recommended Next Order

1. Keep `docs/AI_CONTEXT_INDEX.md` and `docs/PROJECT_CURRENT_STATE.md` as the default AI / Codex entry points.
2. Route docs normalization work through Issue125 in small, scoped PRs.
3. Draft Stage 8 planning separately before any implementation work.
4. Open Stage 8 implementation only after Docs Governance boundaries are explicit.
