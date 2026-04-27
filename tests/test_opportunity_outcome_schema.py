from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_stage6_outcome_required_and_nullable_contract() -> None:
    schema = _load_json(REPO_ROOT / "schemas" / "opportunity_outcome.schema.json")
    required = set(schema["required"])

    assert required == {
        "schema_version",
        "opportunity_id",
        "action_after_gate",
        "outcome_status",
        "data_quality",
        "created_at",
    }
    assert schema["properties"]["trace_id"]["type"] == ["string", "null"]
    assert schema["properties"]["symbol"]["type"] == ["string", "null"]
    assert schema["properties"]["direction"]["type"] == ["string", "null"]


def test_stage6_action_after_gate_is_hard_enum() -> None:
    schema = _load_json(REPO_ROOT / "schemas" / "opportunity_outcome.schema.json")
    enum_values = set(schema["properties"]["action_after_gate"]["enum"])

    assert enum_values == {
        "EXECUTE",
        "WATCH",
        "BLOCK",
        "PENDING_CONFIRM",
        "UNKNOWN",
    }
    assert "PENDING_CONFIRM" in enum_values
    assert "UNKNOWN" in enum_values
    # Audit-only values are allowed for contract completeness, but Stage6 primary stats
    # must keep their existing resolved outcome semantics.


def test_stage6_failure_reason_enum_closed() -> None:
    outcome_schema = _load_json(REPO_ROOT / "schemas" / "opportunity_outcome.schema.json")
    mapping_schema = _load_json(REPO_ROOT / "schemas" / "mapping_attribution.schema.json")

    outcome_failure_enum = set(
        outcome_schema["properties"]["failure_reasons"]["items"]["enum"]
    )
    mapping_failure_enum = set(
        mapping_schema["properties"]["mapping_failure_reason"]["enum"]
    )

    assert "mapping_wrong" in outcome_failure_enum
    assert "insufficient_sample" in outcome_failure_enum
    assert "NON_STANDARD_REASON" not in outcome_failure_enum

    assert "mapping_wrong" in mapping_failure_enum
    assert "insufficient_sample" in mapping_failure_enum
    assert None in mapping_failure_enum
    assert "NON_STANDARD_REASON" not in mapping_failure_enum


def test_mapping_status_rejects_legacy_success_token() -> None:
    mapping_schema = _load_json(REPO_ROOT / "schemas" / "mapping_attribution.schema.json")
    mapping_status_enum = set(mapping_schema["properties"]["mapping_status"]["enum"])

    assert "mapping_success" in mapping_status_enum
    assert "SUCCESS" not in mapping_status_enum
