# PR-7 Rule ↔ Test Mapping

This mapping is complete for PR-7a contract-freeze scope. Rules marked "planned in PR-7b" are intentionally deferred engine/runtime validation items and are not PR-7a acceptance blockers.

| Rule ID | Rule | Test ID | File |
|---|---|---|---|
| S6-R001 | pending must not be labeled hit/miss | S6-011 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R002 | invalid records excluded from primary stats | S6-008 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R003 | monotonicity requires enough sample | S6-013 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R004 | mock/test source excluded from primary stats | S6-016 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R005 | idempotent writes for same key | S6-017 | tests/test_outcome_idempotency.py |
| S6-R006 | replay result consistency | S6-018 | tests/test_outcome_replay_consistency.py |
| S6-R007 | provider info used for attribution only | S6-019 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R008 | BLOCK no-advantage must map neutral_block | S6-007N | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R009 | half-day calendar handling | S6-020 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R010 | no fabricated carry-forward price on halt/no-price | S6-021 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R011 | non-trading day rolls to next valid day | S6-022 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R012 | score bucket detail file must be produced | S6-012/S6-013 | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R013 | WATCH low-evidence must map neutral_watch | S6-005N | *(planned in PR-7b, not covered in PR-7a)* |
| S6-R014 | PENDING_CONFIRM / UNKNOWN allowed for audit only and excluded from primary stats | S6-023 | tests/test_opportunity_outcome_schema.py |
