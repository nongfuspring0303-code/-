# Project Gap Monitor Design

## Purpose

Project Gap Monitor is a read-only scanner that discovers missing modules, broken contracts, stale logs, schema/test/config gaps, frontend visibility gaps, and obvious safety risks.

It does not modify the main trading or execution path.
It does not add any `/api/project/*` write endpoint.
It does not auto-fix code.

## Scope

- `module-registry.yaml`
- `schemas/`
- `configs/`
- `tests/`
- `scripts/`
- `canvas/`
- `logs/`

## Outputs

Running `scripts/project_gap_monitor.py` writes the following runtime artifacts under `logs/` by default:

- `logs/project_gap_report.json`
- `logs/project_gap_report.md`
- `logs/project_gap_state.json`

These are runtime artifacts only and must not be committed.

## Report Contract

- `schema_version`: `project_gap_report.v1`
- `overall_status`: `GREEN | YELLOW | RED`
- `summary`: active counts for `P0`, `P1`, `P2`, and `total_count`
- `delta_vs_prev`: `new_count`, `resolved_count`, `unchanged_count`, `suppressed_count`
- `top_blockers`: active high-severity findings in sorted order
- `findings`: all findings, including suppressed findings

## State Contract

- `schema_version`: `project_gap_state.v1`
- `generated_at`
- `active_dedupe_keys`
- `findings_by_key`

## Deduplication

`dedupe_key = category + module + code + evidence_file + normalized_field`

## Status Rule

- `RED` when any active `P0` finding exists
- `YELLOW` when no active `P0` exists and any active `P1` finding exists
- `GREEN` when no active `P0` or `P1` exists

## Allowlist

`configs/project_gap_monitor_allowlist.yaml` can suppress specific findings by:

- category
- module
- code
- evidence_file
- normalized_field

`allow_p0` must be set explicitly to suppress a `P0` finding.

## Safety Boundary

- No main trading algorithm changes.
- No broker/execution coupling.
- No runtime logs are committed.
- No secrets, tracebacks, or local paths should be emitted in report output.
