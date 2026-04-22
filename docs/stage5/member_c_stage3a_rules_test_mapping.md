# Member C Stage3A Rules to Tests Mapping

## Scope
This mapping covers C-owned Stage3A replay/join/override repair requirements.

| Rule ID | Rule Statement | Test ID | Test Anchor |
| --- | --- | --- | --- |
| R-C-S3A-001 | Replay writer must persist required primary keys (`event_trace_id/request_id/batch_id/event_hash`) for each replay evidence record. | T-C-S3A-001 | `tests/test_member_c_stage3a_replay_join_integrity.py::test_stage3a_replay_primary_keys_complete_without_input_event_hash` |
| R-C-S3A-002 | Replay/join validator must report primary-key completeness and orphan counts for each replay decision path. | T-C-S3A-002 | `tests/test_member_c_stage3a_replay_join_integrity.py::test_stage3a_reports_orphan_replay_when_replay_write_fails` |
| R-C-S3A-003 | Retries with same `request_id` must not duplicate replay writes or execution emits. | T-C-S3A-003 | `tests/test_member_c_stage3a_replay_join_integrity.py::test_stage3a_retry_same_request_id_no_duplicate_replay_or_execution` |
| R-C-S3A-004 | Execute path must remain joinable between `replay_write` and `execution_emit` using required trace keys. | T-C-S3A-004 | `tests/test_member_c_stage3a_replay_join_integrity.py::test_stage3a_execution_join_validation_passes` |
| R-C-S3A-005 | Stage3A acceptance paths must satisfy `orphan_replay_count = 0` under nominal BLOCK/WATCH/PENDING_CONFIRM/EXECUTE flows. | T-C-S3A-005 | `tests/test_member_c_stage3a_replay_join_integrity.py::test_stage3a_acceptance_orphan_replay_zero_on_nominal_paths` |
