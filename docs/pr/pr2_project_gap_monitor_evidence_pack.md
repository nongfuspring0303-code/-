# PR-2 Project Gap Monitor Evidence Pack

- Branch Owner: B
- PR Opener: B
- Main Contributor: B
- Reviewer / Gatekeeper: A

## Scope

- Added a read-only Project Gap Monitor that scans repository source files and local logs for gaps, health issues, hardcode risks, and visibility gaps.
- Kept the main trading and execution algorithm unchanged.
- Kept `/api/project/*` out of scope for PR-2.
- Did not add any write endpoint.
- Did not commit any `logs/` runtime artifacts.

## Files Changed

- `scripts/project_gap_monitor.py`
- `configs/project_gap_monitor_allowlist.yaml`
- `docs/system/project_gap_monitor_design.md`
- `docs/pr/pr2_project_gap_monitor_evidence_pack.md`
- `.github/workflows/ci.yml`
- `tests/test_project_gap_monitor.py`

## Contract

### Report JSON

- `schema_version`: `project_gap_report.v1`
- `overall_status`: `GREEN | YELLOW | RED`
- `summary`: `p0_count`, `p1_count`, `p2_count`, `total_count`
- `delta_vs_prev`: `new_count`, `resolved_count`, `unchanged_count`, `suppressed_count`
- `top_blockers`: active high-severity findings
- `findings`: all findings including suppressed items

### State JSON

- `schema_version`: `project_gap_state.v1`
- `generated_at`
- `active_dedupe_keys`
- `findings_by_key`

### Deduplication

- `dedupe_key = category + module + code + evidence_file + normalized_field`

### Status Rule

- `RED` when any active `P0` finding exists.
- `YELLOW` when no active `P0` exists and any active `P1` finding exists.
- `GREEN` when no active `P0` or `P1` exists.

## Generated Runtime Artifacts

Running `scripts/project_gap_monitor.py` writes:

- `logs/project_gap_report.json`
- `logs/project_gap_report.md`
- `logs/project_gap_state.json`

These are runtime artifacts and are not committed.

## Test Commands

- `python3 -m pytest -q tests/test_project_gap_monitor.py`
- `python3 -m pytest -q tests/test_project_trace_api.py tests/test_full_workflow.py tests/test_project_gap_monitor.py`
- `python3 scripts/verify_execution_no_pytest.py`
- `PYTHONPYCACHEPREFIX=/tmp/python-pycaches python3 -m py_compile scripts/project_gap_monitor.py scripts/project_trace_reader.py scripts/config_api_server.py tests/test_project_gap_monitor.py`

## Test Result

- `tests/test_project_gap_monitor.py`: 11 passed
- Combined regression: `30 passed`
- `scripts/verify_execution_no_pytest.py`: passed
- `py_compile`: passed

## Safety Boundary

- Read-only scanning only.
- No main trading algorithm changes.
- No broker/execution coupling.
- No logs runtime artifacts committed.
- No auto-fix behavior.
- No `/api/project/*` write endpoint added.

## Notes

- The default allowlist only suppresses expected first-run missing report/state artifacts.
- The monitor emits gap findings for missing logs, schema/test/config coverage, frontend contract markers, and health source issues.
- Review by A is still required before merge.
