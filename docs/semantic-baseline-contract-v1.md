# Semantic Baseline Contract v1

This contract is aligned to the current analyzer/test surface in PR #51 and the
runtime handoff contract used by PR #93.
Items that are not part of the current closed loop are intentionally omitted from the contract instead of being pre-declared as required.

## 1. Responsibilities

The semantic layer is only responsible for producing the following fields:

- `event_type`
- `sentiment`
- `confidence`
- `recommended_chain`
- `recommended_stocks`
- `a0_event_strength`
- `expectation_gap`
- `transmission_candidates`
- `fallback_reason`

These outputs may be used by downstream modules as semantic signals, but the semantic layer itself does not own downstream policy or execution decisions.

## 1.1 Runtime Handoff Required Set (v2.2)

For runtime handoff to execution/scorecard, the semantic baseline required set is:

- `sentiment`
- `confidence`
- `recommended_chain`
- `recommended_stocks`
- `a0_event_strength`
- `expectation_gap`
- `transmission_candidates`

If any field from this set is missing in raw semantic output:

- runtime may apply backward-compatible defaults for execution continuity
- but must set `semantic_missing_fields` and `semantic_defaults_applied=true`
- scorecard must expose `ai_missing_fields` from raw-output missing set (not from post-default payload)

## 2. Non-Responsibilities

The semantic layer must not directly modify:

- `score_tier`
- `position_pct`
- `execution_action`
- `final_action`
- `gate_reason_code`
- `state_machine_step`

Any downstream effect on these fields must come from non-semantic modules or explicit downstream policy logic.

## 3. Config Baseline

The semantic configuration baseline is limited to:

- `provider`
- `model`
- `timeout_ms`
- `api_key_env`

These values must be loaded from repository configuration and local environment sources only.

## 4. Key Policy

Allowed key sources:

- environment variables
- `.env.local`

Supported environment selector:

- `api_key_env` in semantic config, defaulting to `ZAI_API_KEY`

Forbidden key sources:

- `~/.bash_profile`
- shell profile auto-loading

The semantic layer must not depend on shell profile side effects for key resolution.

Legacy alias policy:

- legacy aliases are removed in this topic
- `GLM_API_KEY` and `OPENCLAW_GLM_API_KEY` are not contract-supported resolution targets
- callers must migrate to the configured `api_key_env` value

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
  - `execution_action`

## 8. Gate Notes

This contract is the only authority for semantic-baseline boundary decisions during the current topic.
Any file import or diff reduction must be checked against this contract before being accepted into `topic/semantic-baseline`.
