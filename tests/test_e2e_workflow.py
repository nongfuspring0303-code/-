import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner


def _payload():
    return {
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
        "has_opportunity": True,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }


def test_e2e_execute_path():
    out = WorkflowRunner().run(_payload())
    assert out["final"]["action"] == "EXECUTE"
    assert "position" in out
    assert "exit_plan" in out


def test_e2e_human_confirm_pending():
    p = _payload()
    p["require_human_confirm"] = True
    p["human_confirmed"] = False
    out = WorkflowRunner().run(p)
    assert out["final"]["action"] == "PENDING_CONFIRM"
    assert out["human_confirm"]["required"] is True
