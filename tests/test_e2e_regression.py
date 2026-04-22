import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner


def _base_payload():
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "has_opportunity": True,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }


def test_regression_execute(tmp_path):
    runner = WorkflowRunner(request_store_path=str(tmp_path / "ids.txt"), audit_dir=str(tmp_path / "logs"))
    out = runner.run(_base_payload())
    assert out["final"]["action"] == "EXECUTE"


def test_regression_block_liquidity(tmp_path):
    runner = WorkflowRunner(request_store_path=str(tmp_path / "ids2.txt"), audit_dir=str(tmp_path / "logs2"))
    p = _base_payload()
    p.update({"vix": 40, "ted": 130, "spread_pct": 0.02})
    out = runner.run(p)
    assert out["final"]["action"] == "BLOCK"


def test_regression_force_close_dead(tmp_path):
    runner = WorkflowRunner(request_store_path=str(tmp_path / "ids3.txt"), audit_dir=str(tmp_path / "logs3"))
    p = _base_payload()
    p["event_state"] = "Dead"
    out = runner.run(p)
    assert out["final"]["action"] == "FORCE_CLOSE"


def test_regression_watch_fatigue(tmp_path):
    runner = WorkflowRunner(request_store_path=str(tmp_path / "ids4.txt"), audit_dir=str(tmp_path / "logs4"))
    p = _base_payload()
    p["fatigue_index"] = 90
    out = runner.run(p)
    assert out["final"]["action"] == "WATCH"


def test_regression_pending_confirm(tmp_path):
    runner = WorkflowRunner(request_store_path=str(tmp_path / "ids5.txt"), audit_dir=str(tmp_path / "logs5"))
    p = _base_payload()
    p["require_human_confirm"] = True
    p["human_confirmed"] = False
    out = runner.run(p)
    assert out["final"]["action"] == "PENDING_CONFIRM"


def test_regression_duplicate_idempotent_across_restart(tmp_path):
    store = tmp_path / "ids6.txt"
    p = _base_payload()
    p["request_id"] = "REQ-E2E-001"
    runner1 = WorkflowRunner(request_store_path=str(store), audit_dir=str(tmp_path / "logs6"))
    first = runner1.run(p)
    assert first["final"]["action"] in ("EXECUTE", "WATCH", "BLOCK", "FORCE_CLOSE", "PENDING_CONFIRM")
    runner2 = WorkflowRunner(request_store_path=str(store), audit_dir=str(tmp_path / "logs6"))
    second = runner2.run(p)
    assert second["final"]["action"] == "DUPLICATE_IGNORED"
