import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from narrative_state_recognizer import NarrativeStateRecognizer


def _base_payload():
    return {
        "trace_id": "TRC-20260402-0001",
        "event_id": "ME-C-20260402-001.V1.0",
        "evidence_score": 82,
        "consistency_score": 76,
        "freshness_score": 88,
        "confidence": 81,
    }


def test_narrative_state_prefers_upstream_valid_value():
    mod = NarrativeStateRecognizer()
    payload = _base_payload()
    payload["narrative_state"] = "continuation"
    out = mod.run(payload)
    assert out.data["narrative_state"] == "continuation"


def test_narrative_state_invalid_when_contradicted():
    mod = NarrativeStateRecognizer()
    payload = _base_payload()
    payload["contradicted_by_fact"] = True
    out = mod.run(payload)
    assert out.data["narrative_state"] == "invalid"
    assert out.data["transition_valid"] is True


def test_narrative_state_block_recover_from_invalid_with_low_confidence():
    mod = NarrativeStateRecognizer()
    payload = _base_payload()
    payload["previous_narrative_state"] = "invalid"
    payload["confidence"] = 50
    out = mod.run(payload)
    assert out.data["narrative_state"] == "invalid"
    assert out.data["transition_valid"] is False

