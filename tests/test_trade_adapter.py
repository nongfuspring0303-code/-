import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transmission_engine.core.trade_adapter import build_trade_decision


def _gate() -> dict:
    return {
        "asset_validation": {"trade_min": 65.0},
        "mixed_regime_override": {"enabled": False},
    }


def test_build_trade_decision_includes_state_fields():
    payload = {
        "trace_id": "evt_1",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "mixed_regime": False,
        "asset_validation": {"score": 75.0},
        "risk_blocked": False,
        "event_type_lv2": "AI_CAPEX_UP",
        "sectors": [{"name": "科技", "direction": "LONG", "impact_score": 0.8, "confidence": 0.9}],
    }
    out = build_trade_decision(payload, _gate())
    assert out["action"] == "TRADE"
    assert out["state_machine_step"] == "trade_admission"
    assert out["gate_reason_code"] == "ALL_PASSED"
    assert "sector_rankings" in out
    assert "stock_candidates" in out
    assert len(out["stock_candidates"]) <= 5
