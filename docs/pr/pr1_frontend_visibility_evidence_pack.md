# PR-1 Frontend Ultimate v2.1 Data Visibility Evidence Pack

- Branch Owner: B
- PR Opener: B
- Main Contributor: B + C
- Reviewer / Gatekeeper: A

## Scope

- Added read-only project trace visibility APIs under `/api/project/*`.
- Kept execution suggestion advisory-only.
- Did not modify the main trading or execution algorithm.
- Did not add any write endpoint under `/api/project/*`.
- Did not add any `logs/` runtime artifacts to the commit.

## Files Changed

- `scripts/project_trace_reader.py`
- `scripts/config_api_server.py`
- `tests/test_project_trace_api.py`
- `docs/pr/pr1_frontend_visibility_evidence_pack.md`
- `canvas/index.html`
- `canvas/app.js`
- `canvas/styles.css`

## API Contract Impact

- Added `GET /api/project/traces/latest`
- Added `GET /api/project/trace/{trace_id}`
- Added `GET /api/project/scorecards/latest`
- Added `GET /api/project/gap-report`
- Added `GET /api/project/system-health`
- All responses use the project API envelope:

```json
{
  "schema_version": "project.api.v1",
  "status": "ok|empty|partial|error",
  "code": "OK",
  "message": "human readable safe message",
  "trace_id": "evt_xxx",
  "request_id": "req_xxx",
  "generated_at": "UTC ISO timestamp",
  "retryable": false,
  "errors": [],
  "data": {}
}
```

- `/api/project/*` is read-only.
- Bad JSONL rows are skipped safely and do not produce HTTP 500.
- Required-field gaps are surfaced via `errors[]`.
- Optional fields remain `null` or `[]` when missing.
- All generated timestamps are UTC.
- Responses are sanitized and do not expose traceback text.

## Field Matrix v1.2

- Field matrix v1.2 was used as the PR-1 source of truth.
- `suggested_pct_min` and `suggested_pct_max` in `schemas/execution_suggestion.schema.json` are present as numeric properties but are not required fields.
- For trace visibility, the implemented reader uses the matrix-backed paths for:
  - `trace_scorecard.jsonl`
  - `pipeline_stage.jsonl`
  - execution suggestion remains advisory-only
- B sample verified: `trace_scorecard.jsonl` uses `scores.total_score` / `scores.grade`; API adapter maps them to `traceDetail.scorecard.totalScore` / `grade`. A should confirm whether field matrix `backend_path` needs update.
- B sample verified: `pipeline_stage.jsonl` uses `logged_at`; API adapter maps it to `traceDetail.pipeline.timestamp`. A should confirm whether field matrix `backend_path` needs update.

## C Side Frontend Deliverables

- Trace Detail Panel
- LifecycleFatigueCard
- ExecutionSuggestionCard
- PathQualityEvalCard
- TraceScorecardCard
- PipelineStageCard
- ApiErrorCard
- EmptyStateCard

## Frontend Evidence

- `data-module="TraceDetailPanel"` is present on the trace detail root panel.
- `data-key="execution_suggestion.trade_type"` is present in the ExecutionSuggestionCard.
- `data-key="path_quality_eval.composite_score"` is present in the PathQualityEvalCard.
- `data-key="trace_scorecard.final_action"` is present in the TraceScorecardCard.
- `data-key="pipeline_stage.stage"` is present in the PipelineStageCard.
- `data-module="EmptyStateCard"` and `data-key="empty_state"` are present in the global pending / empty trace fallback inside Trace Detail Panel.
- `data-state` is set on every module card and reflects `OK`, `MISSING`, `PENDING`, `STALE`, `PARTIAL`, or `FAILED`.

## Four-State Empty Handling

- `MISSING`: upstream optional fields or modules are not produced, so the card shows `字段未产出 / 当前 trace 无该模块输出`.
- `PENDING`: logs are not ready yet or the latest trace has no module output yet, so the card shows `等待下一轮产出`.
- `STALE`: data exists but is older than the freshness threshold, so the card shows a stale state and keeps the latest visible timestamp.
- `FAILED`: API error or network failure, so the card shows `code`, `message`, and `request_id` only.

## Manual Acceptance

1. Open `canvas/index.html`.
2. Click `最新` to load the latest Trace.
3. Verify Trace Detail Panel, TraceScorecardCard, PipelineStageCard, LifecycleFatigueCard, ExecutionSuggestionCard, PathQualityEvalCard, ApiErrorCard, and EmptyStateCard are visible as appropriate.
4. Verify missing modules render `MISSING` instead of white space.
5. Verify API errors render `FAILED` with `code`, `message`, and `request_id`.
6. Verify the advisory-only banner is visible and does not expose any execution trigger.

## Log Sample Notes

- Local sample logs were present for `logs/trace_scorecard.jsonl` and `logs/pipeline_stage.jsonl`.
- The implementation also tolerates missing logs and returns `empty` or `partial` rather than failing.
- No production-like log artifact was added to the commit.

## Tests

### Commands Run

- `python3 -m pytest -q tests/test_project_trace_api.py`
- `python3 -m pytest -q tests/test_full_workflow.py`
- `python3 scripts/verify_execution_no_pytest.py`
- `python3 -m py_compile scripts/project_trace_reader.py scripts/config_api_server.py tests/test_project_trace_api.py`

### Results Summary

- `tests/test_project_trace_api.py`: passed, 4 passed.
- `tests/test_full_workflow.py`: passed, 9 passed.
- `scripts/verify_execution_no_pytest.py`: passed.
- `py_compile`: the command is clean when run with a separate cache prefix; the default cache location in this sandbox is restricted.

## Risk / Rollback

- C side only changes display logic and does not modify backend contract behavior.
- `lifecycle_fatigue_contract`, `execution_suggestion`, and `path_quality_eval` will show `MISSING` if the current API does not emit them yet.
- B already completed the API layer, and A should still confirm the final field matrix / contract mapping.
- Risk is limited to read-only visibility endpoints, server routing, and frontend rendering.
- Rollback is straightforward:
  - revert `scripts/project_trace_reader.py`
  - revert `scripts/config_api_server.py`
  - revert `tests/test_project_trace_api.py`
- revert `canvas/index.html`
- revert `canvas/app.js`
- revert `canvas/styles.css`
- No trading logic rollback is required because the execution path was not changed.

## Remaining Notes

- `logs/` runtime outputs were intentionally not committed.
- The advisory-only execution suggestion contract was preserved.
- A review by A is still required before PR merge.
