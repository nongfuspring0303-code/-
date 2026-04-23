# Member B Stage5 Review Checklist
**Version**: v1.0  
**Date**: 2026-04-24  
**Owner**: Member B  
**Usage**: Direct review checklist for C-side Stage5 total PR

## 1) File existence checks

- [ ] Scorecard/evaluator output contains B-side required fields (see `member_b_stage5_required_fields.md`)
- [ ] B-side scoring policy is referenced and not overridden
- [ ] Stage5 evidence includes scorecard records for reviewed window

## 2) Field presence checks

- [ ] `trace_id` and `event_hash` are present and readable
- [ ] `sector_candidates`, `ticker_candidates`, `theme_tags` are present
- [ ] `sectors[]`, `sector_impacts`, `stock_candidates`, `mapping_source` are present
- [ ] `final_action` and `final_reason` are present
- [ ] `needs_manual_review`, `placeholder_count`, `non_whitelist_sector_count` are present
- [ ] `ticker_truth_source_hit` and `ticker_truth_source_miss` are present
- [ ] B scores are present: `sector_quality_score`, `ticker_quality_score`, `output_quality_score`, `mapping_acceptance_score`, `b_overall_score`, `b_signoff_ready`

## 3) Scoring behavior checks

- [ ] `non_whitelist_sector_count == 0` or scorecard explicitly fails
- [ ] `ticker_truth_source_miss == 0` or scorecard explicitly fails
- [ ] placeholder leakage threshold (`<=1%`) is enforced
- [ ] fallback/template-collapse paths are not scored as high-quality formal output
- [ ] `b_signoff_ready=true` only when all B quality conditions pass

## 4) Final sign-off checks

- [ ] Rule checks R-B-S5-001 ~ R-B-S5-006 are evidenced
- [ ] B-side sign-off template is filled (`PASS` / `PASS WITH NOTE` / `FAIL`)
- [ ] Blocking items (if any) are listed with minimal remediation actions
- [ ] Evidence paths are explicit and auditable

