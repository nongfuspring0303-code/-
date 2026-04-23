# Member B Stage5 Required Fields
**Version**: v1.0  
**Date**: 2026-04-24  
**Owner**: Member B  
**Scope**: Stage5 B-side required consumption contract (pre-implementation freeze)

## 1) Contract statement

Member B sign-off for Stage5 depends on scorecard/evaluator outputs containing all required fields below.

If C-side evaluator/scorecard does not produce these fields, B-side sign-off cannot be completed.

## 2) Required fields

| Field | B Required | Purpose |
| --- | --- | --- |
| `trace_id` | Yes | Cross-log traceability for mapping review |
| `event_hash` | Yes | Dedup/replay consistency anchor |
| `semantic_event_type` | Yes | Semantic context for mapping validation |
| `sector_candidates` | Yes | Core sector consumption input |
| `ticker_candidates` | Yes | Core ticker consumption input |
| `theme_tags` | Yes | Theme-level output quality review |
| `tradeable` | Yes | Actionability context for acceptance readiness |
| `opportunity_count` | Yes | Opportunity quality and consistency reference |
| `final_action` | Yes | Final decision path context |
| `final_reason` | Yes | Explainability and manual review evidence |
| `sectors[]` | Yes | Final sector output under whitelist rules |
| `sector_impacts` | Yes | Sector impact explainability |
| `stock_candidates` | Yes | Final candidate stock list |
| `mapping_source` | Yes | Mapping provenance for audit |
| `needs_manual_review` | Yes | Review path ratio and quality impact |
| `placeholder_count` | Yes | Placeholder leakage control |
| `non_whitelist_sector_count` | Yes | Whitelist hard-gate measurement |
| `ticker_truth_source_hit` | Yes | Ticker truth-source coverage |
| `ticker_truth_source_miss` | Yes | Ticker truth-source failure detection |
| `sector_quality_score` | Yes | B-side sector quality score |
| `ticker_quality_score` | Yes | B-side ticker quality score |
| `output_quality_score` | Yes | B-side output quality score |
| `mapping_acceptance_score` | Yes | B-side mapping acceptance score |
| `b_overall_score` | Yes | B-side final score aggregation |
| `b_signoff_ready` | Yes | Hard precondition for B sign-off |

## 3) Missing-field policy

Any missing required field is treated as `contract_incomplete` for B-side review.

B-side decision under missing-field condition:
- `PASS`: not allowed
- `PASS WITH NOTE`: not allowed
- `FAIL`: required

