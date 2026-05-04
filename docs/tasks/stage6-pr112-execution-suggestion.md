# Stage6 PR112 Taskbook

## PR
PR112 - execution_suggestion only (human review assist)

## Owner / Reviewer
- Owner: C (implementation)
- Reviewer: A/B (contract + boundary review)

## Deliverables
1. Suggestion contract fields:
   - `trade_type`
   - `entry_condition`
   - `risk_level`
   - `overnight_allowed`
   - `invalidation_condition`
2. Suggestion schema + policy files
3. Rule↔Test mapping for PR112
4. Boundary tests proving no execution-chain consumption

## Non-Negotiable Rules
- No automatic execution behavior from suggestion fields
- No Gate/final_action coupling
- No runtime artifact commits

## Suggested Test Anchors
- `test_execution_suggestion_schema.py`
- `test_execution_suggestion_consumer_boundary.py`
- `test_execution_suggestion_policy_contract.py`

## Exit Criteria
- Contract fields + schema + policy aligned
- CI test step green
- A/B formal review confirms advisory-only boundary
