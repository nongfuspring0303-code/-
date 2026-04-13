# Semantic Baseline Contract v1

## 1. Responsibilities

The semantic layer is only responsible for producing the following fields:

- `event_type`
- `sentiment`
- `confidence`
- `narrative_tags`

These outputs may be used by downstream modules as semantic signals, but the semantic layer itself does not own downstream policy or execution decisions.

## 2. Non-Responsibilities

The semantic layer must not directly modify:

- `score_tier`
- `position_pct`
- `execution action`

Any downstream effect on these fields must come from non-semantic modules or explicit downstream policy logic.

## 3. Config Baseline

The semantic configuration baseline is limited to:

- `provider`
- `model`
- `timeout_ms`
- `fallback_mode`

These values must be loaded from repository configuration and local environment sources only.

## 4. Key Policy

Allowed key sources:

- environment variables
- `.env.local`

Forbidden key sources:

- `~/.bash_profile`
- shell profile auto-loading

The semantic layer must not depend on shell profile side effects for key resolution.

## 5. Observability

On success, fallback, or failure, the semantic layer must expose consistent observability fields:

- `semantic_status`
- `fallback_reason`
- `provider`
- `model`
- `latency_ms`

These fields are required for debugging, review, and rollback analysis.

## 6. Confidence / Severity Boundary

`confidence` is not a direct replacement for `severity`.

Allowed uses of semantic confidence:

- auxiliary signal
- calibration input
- fallback context

Forbidden use:

- using semantic confidence as a direct severity override

## 7. Keyword Bonus Boundary

If keyword bonus remains enabled, it must satisfy all of the following:

- the bonus must be configurable
- the bonus may only affect:
  - `semantic_base_score`
  - `keyword_bonus`
  - `final_semantic_score`
- the bonus must not directly affect:
  - `score_tier`
  - `position_pct`
  - `execution action`

## 8. Gate Notes

This contract is the only authority for semantic-baseline boundary decisions during the current topic.
Any file import or diff reduction must be checked against this contract before being accepted into `topic/semantic-baseline`.
