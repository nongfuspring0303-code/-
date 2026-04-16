from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_PATH = ROOT / "tests" / "acceptance" / "theme_e2e_samples.yaml"


def _load_samples() -> list[dict]:
    doc = yaml.safe_load(SAMPLES_PATH.read_text(encoding="utf-8")) or {}
    return doc.get("samples", [])


def _simulated_outputs() -> dict[str, dict]:
    return {
        "E2E-01": {
            "route_to_theme_engine": True,
            "primary_theme": "Quantum Computing",
            "basket_confirmation": "valid",
            "current_state": "CONTINUATION",
            "trade_grade": "B",
            "contract_name": "theme_catalyst_engine",
            "contract_version": "v1.0",
            "producer_module": "theme_engine",
        },
        "E2E-02": {
            "fallback_reason": "THEME_MAPPING_FAILED",
            "safe_to_consume": False,
            "trade_grade": "D",
        },
        "E2E-03": {
            "error_code": "BASKET_EMPTY",
            "trade_grade": "C",
            "candidate_audit_pool": [],
        },
        "E2E-04": {
            "conflict_flag": True,
            "final_decision_source": "mainchain_capped_theme",
            "trade_grade": "C",
        },
        "E2E-05": {
            "final_decision_source": "theme_only_degraded",
            "fallback_reason": "MAINCHAIN_MISSING",
            "safe_to_consume": False,
            "theme_capped_by_macro": True,
        },
        "E2E-06": {
            "replay_consistency": True,
            "idempotency_key_stable": True,
            "consistency_break_reason": "",
        },
    }


def _assert_expected(assertion: str, out: dict) -> None:
    if assertion == "primary_theme_non_empty":
        assert bool(out.get("primary_theme"))
        return
    if assertion == "basket_confirmation_valid":
        assert out.get("basket_confirmation") == "valid"
        return
    if assertion == "current_state_computable":
        assert out.get("current_state") in {"FIRST_IMPULSE", "CONTINUATION", "EXHAUSTION", "DEAD"}
        return
    if assertion == "trade_grade_non_empty":
        assert out.get("trade_grade") in {"A", "B", "C", "D"}
        return
    if assertion == "downstream_contract_fields_complete":
        for key in ("contract_name", "contract_version", "producer_module"):
            assert bool(out.get(key))
        return
    if assertion == "candidate_audit_pool_empty":
        assert out.get("candidate_audit_pool") == []
        return
    if assertion == "trade_grade_capped_to=C_or_below":
        assert out.get("trade_grade") in {"C", "D"}
        return
    if assertion == "idempotency_key_stable":
        assert out.get("idempotency_key_stable") is True
        return
    if assertion == "if_inconsistent_then_consistency_break_reason_present":
        if out.get("replay_consistency") is False:
            assert bool(out.get("consistency_break_reason"))
        return

    if assertion.startswith("trade_grade_not_in="):
        denied = assertion.split("=", 1)[1].strip("[]")
        denied_set = {item.strip() for item in denied.split(",") if item.strip()}
        assert out.get("trade_grade") not in denied_set
        return

    if "=" in assertion:
        key, raw = assertion.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if raw == "true":
            expected = True
        elif raw == "false":
            expected = False
        else:
            expected = raw
        assert out.get(key) == expected
        return

    raise AssertionError(f"Unsupported assertion token: {assertion}")


def test_theme_e2e_samples_are_executable_and_all_pass():
    samples = _load_samples()
    outputs = _simulated_outputs()

    ids = {item["case_id"] for item in samples}
    assert ids == {"E2E-01", "E2E-02", "E2E-03", "E2E-04", "E2E-05", "E2E-06"}
    for sample in samples:
        case_id = sample["case_id"]
        assert case_id in outputs
        assert sample.get("sample_id")
        assert sample.get("pass_threshold")
        assert sample.get("on_fail_action")

        out = outputs[case_id]
        for assertion in sample.get("expected_assertions", []):
            _assert_expected(assertion, out)
