# Member B Stage5 Rules-Test Mapping
**Version**: v1.0  
**Date**: 2026-04-24  
**Owner**: Member B  
**Scope**: Stage5 B-side rule freeze and planned test anchors

## R-B-S5-001
- Rule Statement:
  - `sectors[]` non-whitelist ratio must be `0`.
- Required Fields:
  - `sectors[]`, `non_whitelist_sector_count`, `sector_quality_score`
- Expected Score Behavior:
  - `non_whitelist_sector_count == 0` keeps sector dimension eligible for pass.
- Fail Condition:
  - `non_whitelist_sector_count > 0` -> hard fail.
- Planned Test Anchor:
  - `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_non_whitelist_sector_score_fails`

## R-B-S5-002
- Rule Statement:
  - Ticker output must be traceable to truth-source pool.
- Required Fields:
  - `ticker_candidates`, `ticker_truth_source_hit`, `ticker_truth_source_miss`, `ticker_quality_score`
- Expected Score Behavior:
  - `ticker_truth_source_miss == 0` and `ticker_truth_source_hit > 0` required for pass.
- Fail Condition:
  - `ticker_truth_source_miss > 0` -> hard fail.
- Planned Test Anchor:
  - `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_ticker_truth_source_miss_fails`

## R-B-S5-003
- Rule Statement:
  - Placeholder leakage rate must be `<= 1%`.
- Required Fields:
  - `placeholder_count`, `output_quality_score`
- Expected Score Behavior:
  - Leakage within threshold keeps output quality eligible for pass.
- Fail Condition:
  - Leakage `> 1%` -> hard fail for output quality.
- Planned Test Anchor:
  - `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_placeholder_leakage_threshold_enforced`

## R-B-S5-004
- Rule Statement:
  - fallback/template collapse must not be disguised as high-quality formal output.
- Required Fields:
  - `final_action`, `final_reason`, `needs_manual_review`, `output_quality_score`, `mapping_acceptance_score`
- Expected Score Behavior:
  - fallback/template-collapse evidence must reduce quality or require review.
- Fail Condition:
  - fallback/template-collapse evidence exists but score remains pass-level without review.
- Planned Test Anchor:
  - `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_signoff_ready_requires_all_quality_conditions`

## R-B-S5-005
- Rule Statement:
  - Scorecard must support B-side mapping acceptance review.
- Required Fields:
  - `trace_id`, `event_hash`, `sector_candidates`, `ticker_candidates`, `theme_tags`, `mapping_source`, `mapping_acceptance_score`
- Expected Score Behavior:
  - Scorecard contains full evidence chain and mapping acceptance score is interpretable.
- Fail Condition:
  - Any core evidence field missing or mapping score missing.
- Planned Test Anchor:
  - `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_required_fields_present`

## R-B-S5-006
- Rule Statement:
  - B-side sign-off can only be established when `b_signoff_ready=true`.
- Required Fields:
  - `b_signoff_ready`, `sector_quality_score`, `ticker_quality_score`, `output_quality_score`, `mapping_acceptance_score`, `b_overall_score`
- Expected Score Behavior:
  - `b_signoff_ready=true` only when all quality conditions pass.
- Fail Condition:
  - `b_signoff_ready=true` while any mandatory quality condition fails.
- Planned Test Anchor:
  - `tests/test_member_b_stage5_scorecard_contract.py::test_stage5_b_signoff_ready_requires_all_quality_conditions`

