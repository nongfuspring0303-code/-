import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ai_signal_adapter import AISignalAdapter


def _payload():
    return {
        "trace_id": "TRC-20260402-0001",
        "event_id": "ME-C-20260402-001.V1.0",
        "evidence_score": 82,
        "consistency_score": 76,
        "freshness_score": 88,
        "confidence": 81,
        "schema_version": "ai_intel_v1",
        "producer": "member-a",
        "generated_at": "2026-04-02T09:30:00Z",
        "model_id": "gpt-x",
        "prompt_version": "p1",
        "temperature": 0.1,
        "timeout_ms": 10000,
    }


def test_ai_signal_adapter_maps_factors_v1():
    mod = AISignalAdapter()
    out = mod.run(_payload())
    assert out.data["A0"] == 82
    assert out.data["A-1"] == 76
    assert out.data["A1"] == 88
    assert out.data["A1.5"] == 81
    assert out.data["mapping_version"] == "factor_map_v1"


def test_ai_signal_adapter_rolls_back_unknown_mapping_version():
    mod = AISignalAdapter()
    payload = _payload()
    payload["mapping_version"] = "factor_map_v9"
    out = mod.run(payload)
    assert out.data["mapping_version"] == "factor_map_v1"


def test_ai_signal_adapter_marks_review_required_when_confidence_low():
    mod = AISignalAdapter()
    payload = _payload()
    payload["confidence"] = 40
    out = mod.run(payload)
    assert out.data["ai_review_required"] is True
    assert out.data["ai_review_passed"] is False

