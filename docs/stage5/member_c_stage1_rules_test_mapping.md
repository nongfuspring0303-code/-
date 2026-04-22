# Member C Stage1 Rules to Tests Mapping

## Scope
This mapping covers C-owned Stage1 evidence-log and gate-contract checks.

| Rule ID | Rule Statement | Test ID | Test Anchor |
| --- | --- | --- | --- |
| R-C-S1-001 | Stage1 must produce 4 classes / 5 evidence files with trace continuity. | T-C-S1-001 | `tests/test_full_workflow.py::test_stage1_evidence_logs_written_with_trace_id` |
| R-C-S1-002 | Contract-bearing payload must block when `has_opportunity` is missing. | T-C-S1-002 | `tests/test_member_c_stage1_contract_gate.py::test_contract_gate_blocks_when_has_opportunity_missing` |
| R-C-S1-003 | Contract-bearing payload must block when provenance fields are partial. | T-C-S1-003 | `tests/test_member_c_stage1_contract_gate.py::test_contract_gate_blocks_when_provenance_partial` |
