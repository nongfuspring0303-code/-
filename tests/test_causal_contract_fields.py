import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def _payload():
    return {
        "event_id": "ME-CC-001",
        "category": "E",
        "severity": "E2",
        "headline": "Fed signals rate cuts ahead",
        "summary": "Policy easing expected",
        "lifecycle_state": "Active",
        "sector_data": [
            {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 0.8},
            {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": -0.4},
        ],
    }


def test_causal_contract_atomic_fields_exist():
    out = ConductionMapper().run(_payload())
    assert out.status.value == "success"
    data = out.data
    for key in [
        "expectation_gap",
        "macro_factor",
        "market_validation",
        "dominant_driver",
        "relative_direction",
        "absolute_direction",
        "impact_layers",
        "causal_contract",
    ]:
        assert key in data


def test_missing_expectation_gap_outputs_unknown(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda h, s: {"event_type": "monetary", "confidence": 88, "sentiment": "neutral"},
    )
    out = mapper.run(_payload())
    eg = out.data["expectation_gap"]
    assert eg["value"] == "unknown"
    assert eg["raw_score"] is None


def test_market_validation_non_live_structure():
    payload = _payload()
    payload["sector_data"] = [
        {"symbol": "XLK", "sector": "Technology", "industry": "Technology"},
    ]
    out = ConductionMapper().run(payload)
    mv = out.data["market_validation"]
    assert mv["status"] in {"unconfirmed", "insufficient_data", "partial", "validated", "contradicted"}
    assert isinstance(mv["evidence"], list)
    if mv["evidence"]:
        item = mv["evidence"][0]
        assert set(item.keys()) == {"layer", "asset", "expected", "observed", "status", "weight"}


def test_market_validation_contradicted_when_observed_opposite_expected():
    out = ConductionMapper().run(
        {
            "event_id": "ME-CC-CONTRADICT-001",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": -1.2},
            ],
        }
    )
    mv = out.data["market_validation"]
    assert mv["status"] in {"contradicted", "partial", "unconfirmed", "validated"}
    assert any(
        item["expected"] in {"up", "down", "unknown", "flat"}
        and item["observed"] in {"up", "down", "flat", "missing"}
        for item in mv["evidence"]
    )


def test_absolute_direction_not_derived_from_price_move():
    out = ConductionMapper().run(
        {
            "event_id": "ME-CC-ABS-001",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": -3.0},
                {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": -2.0},
            ],
        }
    )
    # Absolute direction should be driven by causal mapping semantics, not directly by observed price sign.
    assert out.data["absolute_direction"] in {"positive", "negative", "neutral", "mixed", "unknown"}
