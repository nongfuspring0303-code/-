import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from execution_modules import RiskGatekeeper


def _base_payload():
    return {
        "event_state": "Active",
        "fatigue_index": 20,
        "liquidity_state": "GREEN",
        "spread_multiplier": 1.0,
        "correlation": 0.5,
        "score": 80,
        "severity": "E3",
        "A1": 70,
        "policy_intervention": "NONE",
        "mapping_version": "factor_map_v1",
        "model_id": "gpt-x",
        "prompt_version": "p1",
    }


def test_risk_gatekeeper_ai_timeout_safe_default_watch():
    mod = RiskGatekeeper()
    payload = _base_payload()
    payload["ai_failure_mode"] = "timeout"
    out = mod.run(payload)
    assert out.data["final_action"] == "WATCH"
    assert out.data["first_triggered_gate"] == "G7"


def test_risk_gatekeeper_ai_error_safe_default_block():
    mod = RiskGatekeeper()
    payload = _base_payload()
    payload["ai_failure_mode"] = "error"
    out = mod.run(payload)
    assert out.data["final_action"] == "BLOCK"
    assert out.data["first_triggered_gate"] == "G7"


def test_risk_gatekeeper_ai_review_reject():
    mod = RiskGatekeeper()
    payload = _base_payload()
    payload["ai_review_required"] = True
    payload["ai_review_passed"] = False
    out = mod.run(payload)
    assert out.data["final_action"] == "WATCH"
    assert out.data["first_triggered_gate"] == "G7"
    assert out.data["decision_summary"]["rejection_reason"] == "ai_review_rejected"

