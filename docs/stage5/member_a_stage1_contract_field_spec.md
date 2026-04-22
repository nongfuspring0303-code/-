# Member A Stage1 Contract Field Specification

**Version**: v1.0  
**Date**: 2026-04-22  
**Owner**: Member A (contract owner)

## 1) Scope and ownership

This document is the Stage1 single source of truth for evidence-log contract fields.

- Stage1 implementation owner: Member C
- Stage1 consumption owner: Member B
- Stage1 field/contract owner: Member A

Any rename, semantic change, enum change, required/optional change, or default policy change must be jointly reviewed by A/B/C before merge.

## 2) Stage1 evidence files (4 classes / 5 files)

1. `raw_news_ingest.jsonl`
2. `market_data_provenance.jsonl`
3. `decision_gate.jsonl`
4. `replay_write.jsonl`
5. `execution_emit.jsonl`

## 3) Contract keys and required fields

### 3.1 Global trace keys (required in all 5 files)

- `trace_id`: required, non-empty string
- `event_trace_id`: required, non-empty string
- `request_id`: required key, value may be null
- `batch_id`: required key, value may be null
- `event_id`: required key, value may be null in non-event paths only when upstream has none
- `event_hash`: required, non-empty string once event object is formed

### 3.2 raw_news_ingest.jsonl

Required fields:
- `logged_at`
- `trace_id`
- `event_trace_id`
- `request_id`
- `batch_id`
- `event_id`
- `event_hash`
- `headline`
- `detected_at`
- `source_rank`

Optional fields:
- `source`
- `ingest_seq`
- `process_seq`

### 3.3 market_data_provenance.jsonl

Required fields:
- `logged_at`
- global trace keys
- `market_data_source`
- `market_data_present`
- `market_data_stale`
- `market_data_default_used`
- `market_data_fallback_used`
- `validation_state`

`market_data_source` enum whitelist:
- `payload_direct`
- `payload_derived`
- `missing`
- `default`
- `synthetic_default`
- `fallback`
- `failed`
- `unknown` (only for backward compatibility read paths, not for new writes)

### 3.4 decision_gate.jsonl

Required fields:
- `logged_at`
- global trace keys
- `contract_version`
- `final_action`
- `final_reason`
- `gate_output`
- `output_gate`
- `semantic_event_type`
- `sector_candidates`
- `ticker_candidates`
- `a1_score`
- `theme_tags`
- `tradeable`
- `opportunity_count`

### 3.5 replay_write.jsonl

Required fields:
- `logged_at`
- global trace keys
- `final_action`
- `action_card`

### 3.6 execution_emit.jsonl

Required fields:
- `logged_at`
- global trace keys
- `contract_version`
- `order`
- `execution_receipt`

## 4) OutputGate contract rules (hard gate)

WorkflowRunner entrypoints must carry output-gate contract fields; no full-missing legacy payload may bypass gate checks.

1. `has_opportunity` must exist for every WorkflowRunner entrypoint.
2. If `has_opportunity` exists, the payload must also include:
   - `market_data_present`
   - `market_data_source`
   - `market_data_stale`
   - `market_data_default_used`
   - `market_data_fallback_used`
3. Missing any required field is a contract violation and must produce `gate_contract_missing_*` blockers.
4. Contract violations must yield final gate action `BLOCK`.

No implicit fallback strings (`unknown`, `default`, `N/A`) may bypass contract checks.

## 5) Versioning and compatibility

- Primary contract: `contract_version = v2.2`
- Legacy compatibility: `legacy_contract_version = v1.0`
- Stage1 requires dual-write metadata (`dual_write=true`) in execution payload/result path.

Compatibility window: one minor version.
Any breaking field change requires:
- A/B/C joint review
- updated tests and mapping docs
- explicit migration note in PR

## 6) Acceptance anchors (must stay green)

- `tests/test_full_workflow.py::test_stage1_evidence_logs_written_with_trace_id`
- `tests/test_member_c_stage1_contract_gate.py::test_contract_gate_blocks_when_has_opportunity_missing`
- `tests/test_member_c_stage1_contract_gate.py::test_contract_gate_blocks_when_provenance_partial`
- `tests/test_member_c_stage1_contract_gate.py::test_contract_gate_blocks_when_market_data_source_missing_with_has_opportunity`
- `tests/test_member_c_stage1_contract_gate.py::test_contract_gate_blocks_when_has_opportunity_without_provenance_fields`
- `tests/test_member_a_stage2_gates.py::test_output_gate_blocks_when_full_legacy_contract_signals_are_missing`

## 7) Stage1 A sign-off criteria

A may sign off Stage1 only when:
- this contract file matches runtime behavior,
- required fields are persisted into all 5 evidence logs,
- output-gate hard checks match Section 4,
- test anchors in Section 6 are green.
