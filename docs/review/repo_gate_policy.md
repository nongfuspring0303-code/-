# Repository Gate Policy

**Date**: 2026-04-23  
**Applies to**: `main` branch and all stage-critical pull requests

## Main Branch Protection Rules

The full `main` branch baseline lives in Section 1 below. Use this section as the short navigation entry for branch-protection rules.

## 1. Main branch protection baseline

The `main` branch must remain protected with the following baseline controls:

- No direct pushes to `main`
- No force pushes
- No branch deletions
- Required status checks must pass before merge
- Required pull request approvals must be present before merge
- Stale approvals must be dismissed after new pushes
- The latest push must be approved after review when the PR changes again
- All review conversations must be resolved before merge
- Admin bypass should remain enforced unless explicitly waived for an incident

## 2. Required status checks

See Section 1 for the baseline `main` protection rules.

At minimum, PRs targeting `main` must pass:

- `test`

If a PR introduces stage-specific CI checks, those checks must be added to the required status check list before the PR is allowed to merge.

## 3. Required approvals

See Section 1 for the baseline `main` protection rules.

Baseline merge requirement:

- at least **1 approval**
- code owner review required for files covered by CODEOWNERS

For stage-critical PRs, the default requirement is strengthened by the stage sign-off rules below.

## 4. Stage-specific reviewer / sign-off rules

### Stage 0

- A signs off the contract / gate / baseline / rollback prerequisites
- B reviews and signs off mapping-related sample contracts
- C reviews and signs off log / replay / quarantine evidence

### Stage 1

- A signs off contract / field definitions
- B reviews evidence-log consumption requirements
- C reviews execution / traceability implications when logs are touched

### Stage 2

- A signs off output-gate contract and hard-block rules
- B reviews mapping-protection impact and false-positive / false-negative risk
- C reviews provenance / replay evidence if gate fields affect observability

### Stage 3A

- A signs off replay / join contract and required keys
- B reviews replay field consumption impact on mapping
- C signs off replay / join integrity evidence

### Stage 3B

- A signs off sector / ticker contract and gate boundaries
- B signs off sector whitelist, ticker pool, fallback removal, placeholder cleanup, and template-collapse rules
- C signs off only if trace / join / log evidence is affected

### Stage 4 and later

- Follow the stage owner / reviewer model documented in the relevant stage pack
- Any PR that crosses stage ownership must name every affected stage in the PR body and obtain the corresponding sign-offs

## 5. Merge eligibility

A PR targeting `main` is merge-eligible only when all of the following are true:

- required status checks from Section 1 are green
- required approvals from Section 1 are present
- required sign-offs for the touched stage(s) are recorded
- scope is not mixed with unrelated cleanup or follow-up work
- any process incident noted in `docs/review/` is explicitly acknowledged before merge

## 6. Incident handling

If a PR was merged before formal closure, the following are required:

- record a post-merge incident note
- separate any unrelated follow-up work into its own PR
- do not treat the merged content as proof that the process was followed

See:

- `docs/review/PR86_post_merge_process_incident.md`

## 7. Acceptance metrics script audit gate

For any PR that introduces or updates acceptance / scorecard / metrics / gate-report scripts, the PR must pass the metrics-script credibility audit before merge.

Required policy anchor:

- `docs/review/acceptance_metrics_audit_rule.md`

Merge gate rule:

- If the 5 audit questions in the rule are not fully answered, treat the PR as not merge-ready.
