# Main Baseline Revalidation After PR115 / PR116

## 1. Purpose
This file confirms whether `main` remains a valid baseline for PR117 after PR115 and PR116 have been merged.

## 2. Baseline Metadata
- Repository: `nongfuspring0303-code-org/-`
- Branch: `main`
- Validation Date: `2026-05-07T17:48:04Z`
- Main HEAD SHA: `2925acc3643243821eb5458305f94bb19087b520`
- Included PRs:
  - PR115
  - PR116

## 3. Validation Commands
Validation was run in a clean temporary worktree at `/private/tmp/pr117-baseline` to avoid contamination from pre-existing local runtime artifacts.

- `python3 -m pytest -q`
- `python3 -m pytest -q tests/test_project_gap_monitor.py tests/test_project_trace_api.py tests/test_project_trace_frontend_contract.py`
- `python3 scripts/verify_execution_no_pytest.py`

## 4. Validation Output Summary

### Full pytest
- Result: `FAILED`
- Failure location: `tests/test_multi_event_arbiter.py::test_multi_event_dedup_and_conflict`
- Failure detail: `assert 0 >= 1` for `out["dropped_conflict"]`
- Additional summary: `306 passed` before the failure was reached

### Targeted CI-aligned subset
- Result: `28 passed`
- Command: `python3 -m pytest -q tests/test_project_gap_monitor.py tests/test_project_trace_api.py tests/test_project_trace_frontend_contract.py`

### Execution-layer verification
- Result: `OK: execution-layer fallback verification passed`
- Command: `python3 scripts/verify_execution_no_pytest.py`

## 5. Evidence Path Check
Confirmed present:
- `docs/pr/pr1_frontend_visibility_evidence_pack.md`
- `docs/pr/pr2_project_gap_monitor_evidence_pack.md`
- `docs/pr/post_merge_evidence/pr115_post_merge_evidence_pack.md`
- `docs/pr/post_merge_evidence/pr116_post_merge_evidence_pack.md`

## 6. Main Baseline Risk Assessment

### Code runtime risk
- LOW for PR115/PR116-related code paths because the targeted subset passed in a clean worktree.
- ONE unrelated full-suite failure remains in `tests/test_multi_event_arbiter.py::test_multi_event_dedup_and_conflict`.

### Test coverage risk
- MEDIUM because full-suite pytest is not green in the current baseline.
- The targeted CI-aligned subset is green.

### CI governance risk
- LOW for the merged PR115/PR116 evidence itself.
- MEDIUM for main-baseline readiness because full-suite revalidation is not fully green.

### PR117 dependency risk
- MEDIUM until the unrelated baseline failure is triaged or explicitly accepted.
- PR117 should rebase from the latest main after this evidence PR is merged.

## 7. Gate Decision for PR117
- Is PR117 allowed to merge before this PR? NO
- Is PR117 allowed to merge after this PR if baseline PASS? YES
- Required action for PR117: rebase / update from latest main after this evidence PR is merged

## 8. Final Conclusion
- WARN

### Note
- The baseline revalidation is informative but not fully green because the full pytest suite still fails on an unrelated arbiter test.
- The PR115 / PR116-specific subset and the execution-layer verification both pass.
