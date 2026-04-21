# Stage 5 Execution Pack

This folder holds execution-level governance docs for the EDT phase-5 rollout.

## Canonical Docs
- `EDT_阶段-负责人矩阵_v1.0_2026-04-21.md`

## Member A Immediate Scope
- Freeze contract and gate prerequisites before implementation.
- Define v2.2 feature flags and rollback ownership.
- Freeze baseline metric schema and stress baseline schema.
- Provide rollback sanitization entrypoint (`scripts/rollback_sanitize_v22.py`).

## Start Order
1. Confirm Go/No-Go prerequisites are complete.
2. Freeze baseline snapshots.
3. Freeze flag defaults and rollback triggers.
4. Start stage-2 blocker fixes with joint review touchpoints.

## Freeze Command
- `python3 scripts/freeze_stage0_baseline.py`
