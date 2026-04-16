import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from theme_gate_policy import (
    REQUIRED_ERROR_CODES,
    apply_theme_gate_constraints,
    load_theme_error_codebook,
    validate_theme_contract,
    validate_theme_error_codebook,
)


def test_theme_error_codebook_contains_required_codes():
    codebook = load_theme_error_codebook()
    errors = validate_theme_error_codebook(codebook)

    assert errors == []
    assert set(REQUIRED_ERROR_CODES).issubset(codebook["codes"].keys())


def test_unsafe_output_forces_degraded_and_prohibits_execute():
    payload = {
        "contract_name": "theme_catalyst_engine",
        "contract_version": "v1.0",
        "producer_module": "theme_engine",
        "safe_to_consume": False,
        "error_code": "CONFIG_MISSING",
        "fallback_reason": "CONFIG_MISSING",
        "degraded_mode": True,
        "trade_grade": "B",
        "conflict_flag": False,
    }

    gate = apply_theme_gate_constraints(payload)

    assert gate["final_action"] == "DEGRADED"
    assert gate["prohibit_execute"] is True
    assert validate_theme_contract(gate) == []


def test_conflict_flag_blocks_trade_grade_a_without_letting_a_pass():
    payload = {
        "contract_name": "theme_catalyst_engine",
        "contract_version": "v1.0",
        "producer_module": "theme_engine",
        "safe_to_consume": True,
        "error_code": "THEME_MAPPING_FAILED",
        "fallback_reason": "THEME_MAPPING_FAILED",
        "degraded_mode": True,
        "trade_grade": "A",
        "conflict_flag": True,
    }

    gate = apply_theme_gate_constraints(payload)

    assert gate["trade_grade"] == "C"
    assert gate["final_action"] == "BLOCK"
    assert gate["prohibit_execute"] is True
    assert validate_theme_contract(gate) == []


def test_safe_to_consume_false_requires_fallback_reason():
    payload = {
        "contract_name": "theme_catalyst_engine",
        "contract_version": "v1.0",
        "producer_module": "theme_engine",
        "safe_to_consume": False,
        "error_code": "CONFIG_INVALID",
        "degraded_mode": True,
        "trade_grade": "B",
        "conflict_flag": False,
    }

    errors = validate_theme_contract(payload)

    assert "fallback_reason_required_when_safe_to_consume_false" in errors


def test_validate_theme_contract_requires_producer_module():
    payload = {
        "contract_name": "theme_catalyst_engine",
        "contract_version": "v1.0",
        "safe_to_consume": True,
        "error_code": "CONFIG_INVALID",
        "fallback_reason": "CONFIG_INVALID",
        "degraded_mode": True,
        "trade_grade": "B",
        "conflict_flag": False,
    }

    errors = validate_theme_contract(payload)

    assert "missing_required_field:producer_module" in errors
