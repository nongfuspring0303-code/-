# Stage6 PR-7b Attribution Rules
# B Member Rule Contract

## 1. Scope

This document is owned by Member B.
It defines attribution rules and expected outcomes for Stage6 PR-7b.
It does not implement engine logic.
It does not modify Gate, execution, workflow runner, final_action, schemas, or configs.

## 2. Single Source of Truth

All thresholds must come from `configs/outcome_scoring_policy.yaml`.
Metric definitions must align with `configs/metric_dictionary.yaml`.
Schema enums must align with PR97 schema files.
`expected_outcomes.yaml` is the fixture-level test contract owned by Member B.

Python engine must not use silent default thresholds such as `thresholds.get("xxx", 0.02)`.
Missing required policy fields must fail fast.

## 3. EXECUTE LONG / SHORT Outcome Rules

### LONG

If `t5_return >= long_hit_return_t5` OR `alpha_t5 >= long_hit_alpha_t5`:

```text
outcome_label = hit
```

If `t5_return <= long_miss_return_t5` OR `alpha_t5 <= long_miss_alpha_t5`:

```text
outcome_label = miss
```

Otherwise:

```text
outcome_label = neutral
```

### SHORT

If `t5_return <= short_hit_return_t5` OR `alpha_t5 <= short_hit_alpha_t5`:

```text
outcome_label = hit
```

If `t5_return >= short_miss_return_t5` OR `alpha_t5 >= short_miss_alpha_t5`:

```text
outcome_label = miss
```

Otherwise:

```text
outcome_label = neutral
```

All thresholds must come from:

```text
configs/outcome_scoring_policy.yaml -> thresholds
```

## 4. WATCH Outcome Rules

If hypothetical outcome would have been hit:

```text
outcome_label = missed_opportunity
```

If hypothetical outcome would have been miss:

```text
outcome_label = correct_watch
```

If outcome is non-significant or evidence is insufficient:

```text
outcome_label = neutral_watch
```

WATCH does not mean trade execution. It only means post-hoc validation of whether watching was correct.

## 5. BLOCK Outcome Rules

If hypothetical outcome would have been miss:

```text
outcome_label = correct_block
```

If hypothetical outcome would have been hit:

```text
outcome_label = overblocked
```

If outcome is non-significant or no clear tradable edge:

```text
outcome_label = neutral_block
```

BLOCK does not mean shorting. It only means post-hoc attribution after system blocking.

## 6. Alpha / Benchmark Rules

```text
alpha_t5 = return_t5 - benchmark_return_t5
```

Rules:

- `benchmark_missing` records may remain auditable.
- `benchmark_missing` must not enter alpha primary stats.
- `default_market` benchmark must not silently enter alpha primary stats.
- If `default_market` is used for readability, it must be marked degraded and excluded from alpha primary stats.

## 7. Score Bucket Monotonicity Rules

Default buckets:

- `80_PLUS`
- `60_79`
- `40_59`
- `LT_40`

Primary metric:

- `avg_alpha_t5`

Secondary metric:

- `hit_rate_t5`

Statuses:

- `passed`
- `passed_with_warning`
- `failed`
- `insufficient_sample`

Rules:

```text
If any key bucket sample_size < min_bucket_sample_size:
  status = insufficient_sample

If total sample size < min_total_sample_size:
  status = insufficient_sample

If avg_alpha_t5 is monotonic and hit_rate_t5 is monotonic:
  status = passed

If avg_alpha_t5 is monotonic but hit_rate_t5 is not monotonic:
  status = passed_with_warning

If avg_alpha_t5 is not monotonic:
  status = failed
```

`min_bucket_sample_size` and `min_total_sample_size` must come from `configs/outcome_scoring_policy.yaml -> stats`.
They must not be read from `data_quality`.
They must not use Python defaults.

## 8. Failure Reason Attribution Rules

Formal `failure_reason` enum may only use:

- `mapping_wrong`
- `timing_wrong`
- `market_rejected`
- `source_bad`
- `risk_too_strict`
- `risk_too_loose`
- `provider_bad`
- `market_data_bad`
- `score_not_predictive`
- `gate_rule_wrong`
- `execution_missing`
- `join_key_missing`
- `benchmark_missing`
- `insufficient_sample`

Rules:

- `primary_failure_reason` is for primary attribution.
- `failure_reasons[]` is for compound attribution.
- If only one failure reason exists, `primary_failure_reason` must equal `failure_reasons[0]`.
- If no failure reason exists, `primary_failure_reason` must be null and `failure_reasons` must be `[]`.

## 9. Data Quality and Stats Inclusion Rules

| data_quality / state | Primary stats | Alpha primary stats | Hit/miss allowed | Notes |
|---|---|---|---|---|
| valid | yes | yes if benchmark valid | yes | normal records |
| degraded | no by default | no by default | no if evidence insufficient | audit/degraded stats only |
| invalid | no | no | no | report only |
| pending | no | no | no | wait for maturity |
| PENDING_CONFIRM | no | no | no | audit-only `action_after_gate` |
| UNKNOWN | no | no | no | audit-only `action_after_gate` |
| mock/test | no | no | no | rejected from primary stats |
| benchmark_missing | maybe valid/degraded for non-alpha | no | depends on return evidence | excluded from alpha primary |

## 10. Audit-only action_after_gate States

`PENDING_CONFIRM` and `UNKNOWN` may be persisted for auditability.
They must not emit hit or miss.
They must not enter primary stats.
They must not enter alpha primary stats.
They must not enter score monotonicity primary stats.
They must be `data_quality=degraded` or `data_quality=invalid`.
They must not change Gate, execution, or final_action semantics.

## 11. Expected Outcomes Fixture Contract

`tests/fixtures/stage6/expected_outcomes.yaml` is owned by Member B.
It is the expected outcome contract for Member C's engine tests.
C's pytest must validate generated outcomes against this YAML.
The YAML must not be only documentation.

## 12. B Member Sign-off Checklist

- [ ] EXECUTE LONG / SHORT rules are defined
- [ ] WATCH rules are defined
- [ ] BLOCK rules are defined
- [ ] alpha / benchmark rules are defined
- [ ] score monotonicity rules are defined
- [ ] failure_reason enum is aligned with PR97
- [ ] data_quality inclusion rules are defined
- [ ] PENDING_CONFIRM / UNKNOWN audit-only rules are defined
- [ ] expected_outcomes.yaml covers all required cases
- [ ] expected_outcomes.yaml is used by pytest
- [ ] no engine logic was modified by Member B

## 13. C Member Required Fixes / Review Notes

Engine must not use `thresholds.get("xxx", default_value)` for hit/miss thresholds.
Engine must read thresholds from `policy["thresholds"]`.
Engine must read `min_bucket_sample_size` and `min_total_sample_size` from `policy["stats"]`.
Missing required policy fields must fail fast.
