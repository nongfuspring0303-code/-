import sys
from datetime import datetime, timezone
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner


def test_full_workflow_execute():
    payload = {
        "headline": "Fed announces emergency liquidity action after tariff shock",
        "source": "https://www.reuters.com/markets/us/example",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 24,
        "vix_change_pct": 20,
        "spx_move_pct": 1.8,
        "sector_move_pct": 3.0,
        "sequence": 1,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
    }
    out = FullWorkflowRunner().run(payload)
    assert "intel" in out
    assert "analysis" in out
    assert "execution" in out
    assert "opportunity_update" in out["analysis"]
    assert out["execution"]["final"]["action"] in ("EXECUTE", "WATCH", "BLOCK", "FORCE_CLOSE", "PENDING_CONFIRM")


def test_full_workflow_persists_incremented_retry_count():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "event_states.db"
        runner = FullWorkflowRunner(state_db_path=str(db_path))
        payload = {
            "headline": "Fed announces emergency liquidity action after tariff shock",
            "source": "https://www.reuters.com/markets/us/example",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vix": 24,
            "vix_change_pct": 20,
            "spx_move_pct": 1.8,
            "sector_move_pct": 3.0,
            "sequence": 1,
            "account_equity": 100000,
            "entry_price": 100.0,
            "risk_per_share": 2.0,
            "direction": "long",
        }

        first = runner.run(payload)
        runner.run(payload)

        event_id = first["intel"]["event_object"]["event_id"]
        state = runner.state_store.get_state(event_id)
        assert state is not None
        assert state["retry_count"] == 2
        assert state["metadata"]["category"] == first["intel"]["event_object"]["category"]
