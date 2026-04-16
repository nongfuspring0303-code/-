import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_theme_contract_mapping_exists_and_covers_required_fields():
    path = ROOT / "schemas" / "theme_contract_mapping.yaml"
    assert path.exists()

    doc = _load_yaml(path)
    fields = {item["field"] for item in doc.get("fields", [])}
    required = {
        "primary_theme",
        "current_state",
        "continuation_probability",
        "trade_grade",
        "candidate_audit_pool",
        "conflict_flag",
        "conflict_type",
        "final_decision_source",
        "macro_regime",
        "theme_capped_by_macro",
        "macro_override_reason",
        "final_trade_cap",
        "fallback_reason",
        "safe_to_consume",
        "contract_name",
        "contract_version",
        "producer_module",
    }
    assert required.issubset(fields)


def test_theme_contract_envelope_has_frozen_identity_and_versioning_policy():
    path = ROOT / "schemas" / "theme_contract_envelope.yaml"
    assert path.exists()

    doc = _load_yaml(path)
    envelope = doc.get("envelope", {})
    assert envelope.get("contract_name", {}).get("const") == "theme_catalyst_engine"
    assert envelope.get("contract_version", {}).get("const") == "v1.0"
    assert envelope.get("producer_module", {}).get("const") == "theme_engine"

    compat_window = doc.get("compatibility_window", {})
    assert compat_window.get("required_for_breaking_change") is True
    assert compat_window.get("recommended_window") == "1_minor_version"


def test_theme_e2e_samples_cover_6_required_cases():
    path = ROOT / "tests" / "acceptance" / "theme_e2e_samples.yaml"
    assert path.exists()

    doc = _load_yaml(path)
    samples = doc.get("samples", [])
    ids = {item.get("case_id") for item in samples}
    assert ids == {"E2E-01", "E2E-02", "E2E-03", "E2E-04", "E2E-05", "E2E-06"}

    for sample in samples:
        assert sample.get("sample_id")
        assert sample.get("pass_threshold")
        assert sample.get("on_fail_action")


def test_risk_gatekeeper_schema_accepts_theme_output_contract():
    path = ROOT / "schemas" / "risk_gatekeeper.json"
    schema = json.loads(path.read_text(encoding="utf-8"))

    input_props = schema["input"]["properties"]
    assert "theme_output" in input_props

    theme_output = input_props["theme_output"]["properties"]
    for field in (
        "safe_to_consume",
        "fallback_reason",
        "contract_name",
        "contract_version",
        "producer_module",
        "conflict_flag",
        "final_decision_source",
        "macro_regime",
        "theme_capped_by_macro",
        "final_trade_cap",
    ):
        assert field in theme_output
