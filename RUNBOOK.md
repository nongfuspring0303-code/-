# Maintainer Runbook

## Purpose

This runbook defines maintainer-facing operational boundaries for docs governance, project health monitoring, and audit tracking.

## Source of Truth Order

1. `docs/PROJECT_CURRENT_STATE.md`
2. `docs/AI_CONTEXT_INDEX.md`
3. `docs/stage8/news_to_accurate_stock_pool_implementation_readiness.md`
4. `docs/stage8/news_to_accurate_stock_pool_contract_matrix.md`
5. `docs/stage8/news_to_accurate_stock_pool_phase0_interface_freeze.md`

If these conflict with old planning notes, follow the current-state and merged-contract docs first.

## Ops Boundary

- `scripts/project_gap_monitor.py` is diagnostics-only and read-only.
- `scripts/local_daily_project_monitor.sh` is local operations tooling only.
- Monitor outputs are not release authority and not trading authority.
- Do not route monitor outputs directly into runtime decision surfaces.

## Runtime Artifact Hygiene

Do not commit runtime artifacts under `logs/`, including:

- `logs/project_gap_report.json`
- `logs/project_gap_report.md`
- `logs/project_gap_state.json`
- `logs/local_project_monitor.log`

## Hard Non-Touch Boundaries for Docs-Only Work

- execution
- broker
- final_action
- release authority escalation to `valid`

## Stage 8 Planning Boundary

- Stage 8 docs define planning contracts and readiness gates.
- They do not authorize implementation by themselves.
- Keep shadow-only and advisory-only constraints explicit in review notes.

## PR Review Checklist (Docs-Governance)

- latest head checked
- CI state checked
- scope in PR body matches diff
- no runtime authority wording drift
- no planning doc presented as production authority
- no historical file deletion without replacement index
