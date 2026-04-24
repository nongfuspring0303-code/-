# Acceptance Metrics Audit Rule

**Date**: 2026-04-25  
**Applies to**: acceptance / scorecard / metrics / gate report scripts and their review/PR closure process

## 1. Purpose

This rule closes a review blind spot: metrics scripts must be auditable and trustworthy before their outputs are accepted as closure evidence.

If this audit is not completed, the script output cannot be used as final acceptance evidence.

## 2. Mandatory 5-question audit

For each acceptance/scorecard/metrics/gate-report script, reviewers must record explicit answers to all five questions:

1. What are the exact input fields for this metric?
2. Is the metric computed from structured fields or string matching?
3. Is there any fallback? If yes, can it create false positives/false negatives?
4. Is there a minimal test case that covers false-positive / false-negative risk?
5. Can every reported number be traced back to raw structured logs?

Any missing answer means audit **FAIL**.

## 3. Pass criteria

Audit can be marked PASS only when:

- all five questions are answered clearly;
- structured-field judgment is the primary path for gate/acceptance-critical metrics;
- fallback behavior is controlled and documented;
- at least one minimal anti-misjudgment test exists;
- metric artifacts are traceable to raw structured logs.

## 4. Review evidence format

For each audited script, include:

- Script path
- Metric name(s)
- Input field list
- Main decision path (structured / string / fallback)
- Test command and result
- Artifact path and traceability statement
- Final audit conclusion (`PASS / PASS WITH NOTE / FAIL`)
