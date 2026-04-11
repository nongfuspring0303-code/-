import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transmission_engine.core.state_machine import evaluate_state


def _gate_policy() -> dict:
    return {
        "asset_validation": {"trade_min": 65.0},
        "mixed_regime_override": {"enabled": False},
    }


def test_data_integrity_blocks_when_missing_required_fields():
    out = evaluate_state({"trace_id": "x"}, _gate_policy())
    assert out["action"] == "NO_ACTION"
    assert out["state_machine_step"] == "data_integrity"
    assert out["gate_reason_code"] == "MISSING_FIELDS"


def test_mixed_regime_returns_watch_when_override_disabled():
    event = {
        "trace_id": "t1",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "mixed_regime": True,
    }
    out = evaluate_state(event, _gate_policy())
    assert out["action"] == "WATCH"
    assert out["state_machine_step"] == "mixed_regime"


def test_trade_when_all_gates_pass():
    event = {
        "trace_id": "t2",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "mixed_regime": False,
        "asset_validation": {"score": 70.0},
        "risk_blocked": False,
    }
    out = evaluate_state(event, _gate_policy())
    assert out["action"] == "TRADE"
    assert out["state_machine_step"] == "trade_admission"
    assert out["gate_reason_code"] == "ALL_PASSED"


def test_mixed_regime_override_enabled_but_not_meeting_thresholds_returns_watch():
    gate = {
        "asset_validation": {"trade_min": 65.0},
        "mixed_regime_override": {
            "enabled": True,
            "asset_validation_min": 75.0,
            "path_dominance_min": 75.0,
            "sector_gap_min": 15.0,
        },
    }
    event = {
        "trace_id": "t3",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "mixed_regime": True,
        "asset_validation": {"score": 80.0},
        "path_dominance": {"score": 70.0},
        "sector_top1_top2_gap": 20.0,
        "risk_blocked": False,
    }
    out = evaluate_state(event, gate)
    assert out["action"] == "WATCH"
    assert out["state_machine_step"] == "mixed_regime"
    assert out["gate_reason_code"] == "MIXED_REGIME"


def test_mixed_regime_override_enabled_and_met_can_trade():
    gate = {
        "asset_validation": {"trade_min": 65.0},
        "mixed_regime_override": {
            "enabled": True,
            "asset_validation_min": 75.0,
            "path_dominance_min": 75.0,
            "sector_gap_min": 15.0,
        },
    }
    event = {
        "trace_id": "t4",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "mixed_regime": True,
        "asset_validation": {"score": 80.0},
        "path_dominance": {"score": 82.0},
        "sector_top1_top2_gap": 18.0,
        "risk_blocked": False,
    }
    out = evaluate_state(event, gate)
    assert out["action"] == "TRADE"
    assert out["state_machine_step"] == "trade_admission"
