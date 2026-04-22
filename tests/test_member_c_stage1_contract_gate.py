import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner


def _base_payload() -> dict:
    return {
        "A0": 40,
        "A-1": 70,
        "A1": 85,
        "A1.5": 65,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 20,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
        "symbol": "SPY",
    }


def test_contract_gate_blocks_when_has_opportunity_missing(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c1.txt"),
        audit_dir=str(tmp_path / "logs_c1"),
    )
    payload = _base_payload()
    payload.update(
        {
            "market_data_present": True,
            "market_data_stale": False,
            "market_data_default_used": False,
            "market_data_fallback_used": False,
        }
    )

    out = runner.run(payload)

    assert out["final"]["action"] == "BLOCK"
    assert "gate_contract_missing_has_opportunity" in out["final"]["reason"]


def test_contract_gate_blocks_when_provenance_partial(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c2.txt"),
        audit_dir=str(tmp_path / "logs_c2"),
    )
    payload = _base_payload()
    payload.update(
        {
            "has_opportunity": True,
            "market_data_present": True,
            "market_data_stale": True,
            "market_data_default_used": False,
        }
    )

    out = runner.run(payload)

    assert out["final"]["action"] == "BLOCK"
    assert "gate_contract_missing_market_data_fallback_used" in out["final"]["reason"]
