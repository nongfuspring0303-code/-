# Member B Stage5 Scoring Policy
**Version**: v1.0  
**Date**: 2026-04-24  
**Owner**: Member B  
**Scope**: Stage5 B-side scoring policy freeze (pre-implementation package)

## 1) Purpose and boundary

This document freezes Member B scoring policy for Stage5 so B-side review can be executed immediately when C-side total implementation PR is opened.

B-side scoring scope only includes:
- sector quality
- ticker quality
- output quality
- mapping acceptance readiness

Out of scope for B:
- A-side Gate/Safety/Audit completeness scoring
- C-side provider/freshness/traceability scoring
- Any evaluator or dashboard implementation details

## 2) Score model (B-side only)

`b_overall_score = min(sector_quality_score, ticker_quality_score, output_quality_score, mapping_acceptance_score)`

Pass gate:
- `b_overall_score >= 80`
- `b_signoff_ready = true`

## 3) Scoring dimensions and rules

### 3.1 Sector quality (`sector_quality_score`)

Base score: 100  
Deductions:
- `non_whitelist_sector_count > 0`: `-100` (hard fail)
- `sectors[]` missing or empty: `-100` (hard fail)
- `sector_impacts` missing or empty: `-40`
- `mapping_source` missing: `-20`

Pass condition:
- `non_whitelist_sector_count == 0`
- `sectors[]` present and non-empty
- `sector_quality_score >= 80`

### 3.2 Ticker quality (`ticker_quality_score`)

Base score: 100  
Deductions:
- `ticker_truth_source_miss > 0`: `-100` (hard fail)
- `ticker_candidates` missing or empty: `-100` (hard fail)
- `stock_candidates` missing or empty: `-40`
- `ticker_truth_source_hit == 0`: `-60`

Pass condition:
- `ticker_truth_source_miss == 0`
- `ticker_truth_source_hit > 0`
- `ticker_quality_score >= 80`

### 3.3 Output quality (`output_quality_score`)

Base score: 100  
Deductions:
- `placeholder_count > 0`: `-100` (hard fail when leakage >1%)
- `needs_manual_review = true`: `-15` (soft deduction, not auto-fail)
- `final_action` missing: `-40`
- `final_reason` missing: `-40`
- `semantic_event_type` missing: `-20`
- `theme_tags` missing or empty: `-20`

Pass condition:
- placeholder leakage rate `<= 1%`
- `output_quality_score >= 80`

### 3.4 Mapping acceptance readiness (`mapping_acceptance_score`)

Base score: 100  
Deductions:
- Any hard-fail in sector/ticker/output dimensions: `-100`
- `trace_id` missing: `-40`
- `event_hash` missing: `-40`
- `opportunity_count` missing: `-20`
- `tradeable` missing: `-20`

Pass condition:
- Core mapping evidence fields all present
- `mapping_acceptance_score >= 80`

## 4) Sign-off policy

B-side sign-off can only be PASS when all conditions below are met:
- `sector_quality_score >= 80`
- `ticker_quality_score >= 80`
- `output_quality_score >= 80`
- `mapping_acceptance_score >= 80`
- `b_overall_score >= 80`
- `b_signoff_ready = true`

Otherwise:
- PASS WITH NOTE: soft-risk remains but no hard-fail rule violated
- FAIL: any hard-fail rule violated

