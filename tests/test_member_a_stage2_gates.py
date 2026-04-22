import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner
from workflow_runner import WorkflowRunner


def _strong_payload() -> dict:
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


def test_output_gate_blocks_execute_when_opportunity_missing(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_a1.txt"),
        audit_dir=str(tmp_path / "logs_a1"),
    )
    payload = _strong_payload()
    payload.update(
        {
            "has_opportunity": False,
            "market_data_present": True,
            "market_data_source": "payload_direct",
            "market_data_stale": False,
            "market_data_default_used": False,
            "market_data_fallback_used": False,
        }
    )

    out = runner.run(payload)

    assert out["final"]["action"] == "WATCH"
    assert "missing_opportunity" in out["final"]["reason"]


def test_output_gate_blocks_execute_when_market_data_stale(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_a2.txt"),
        audit_dir=str(tmp_path / "logs_a2"),
    )
    payload = _strong_payload()
    payload.update(
        {
            "has_opportunity": True,
            "market_data_present": True,
            "market_data_source": "payload_direct",
            "market_data_stale": True,
            "market_data_default_used": False,
            "market_data_fallback_used": False,
        }
    )

    out = runner.run(payload)

    assert out["final"]["action"] == "WATCH"
    assert "market_data_stale" in out["final"]["reason"]


def test_output_gate_blocks_when_contract_fields_are_missing(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_a2b.txt"),
        audit_dir=str(tmp_path / "logs_a2b"),
    )
    payload = _strong_payload()
    payload.update(
        {
            "has_opportunity": True,
            "market_data_source": "payload_direct",
        }
    )
    payload.pop("market_data_present", None)

    out = runner.run(payload)

    assert out["final"]["action"] == "BLOCK"
    assert "gate_contract_missing_market_data_present" in out["final"]["reason"]


def test_output_gate_blocks_when_full_legacy_contract_signals_are_missing(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_a2_legacy.txt"),
        audit_dir=str(tmp_path / "logs_a2_legacy"),
    )
    payload = _strong_payload()
    for field in (
        "has_opportunity",
        "market_data_present",
        "market_data_source",
        "market_data_stale",
        "market_data_default_used",
        "market_data_fallback_used",
        "tradeable",
    ):
        payload.pop(field, None)

    out = runner.run(payload)

    assert out["final"]["action"] == "BLOCK"
    assert "gate_contract_missing_has_opportunity" in out["final"]["reason"]


def test_output_gate_blocks_when_only_has_opportunity_is_provided(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_a2c.txt"),
        audit_dir=str(tmp_path / "logs_a2c"),
    )
    payload = _strong_payload()
    payload.update(
        {
            "has_opportunity": True,
        }
    )
    for field in (
        "market_data_present",
        "market_data_source",
        "market_data_stale",
        "market_data_default_used",
        "market_data_fallback_used",
        "tradeable",
    ):
        payload.pop(field, None)

    out = runner.run(payload)

    assert out["final"]["action"] == "BLOCK"
    assert "gate_contract_missing_market_data_present" in out["final"]["reason"]
    assert "gate_contract_missing_market_data_source" in out["final"]["reason"]


def test_enforce_resolved_symbol_blocks_unknown_symbol(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_a3.txt"),
        audit_dir=str(tmp_path / "logs_a3"),
    )
    payload = _strong_payload()
    payload.pop("symbol", None)
    payload.update(
        {
            "has_opportunity": True,
            "market_data_present": True,
            "market_data_source": "payload_direct",
            "market_data_stale": False,
            "market_data_default_used": False,
            "market_data_fallback_used": False,
            "enforce_resolved_symbol": True,
            "target_leader": [],
            "target_etf": [],
            "target_sector": [],
            "target_followers": [],
        }
    )

    out = runner.run(payload)

    assert out["final"]["action"] == "WATCH"
    assert "missing_tradeable_symbol" in out["final"]["reason"]


def test_full_workflow_no_fake_price_default_blocks_execute():
    payload = {
        "headline": "Macro headline without usable market context",
        "source": "https://example.com/news",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_data_source": "failed",
        "market_data_stale": True,
    }

    out = FullWorkflowRunner().run(payload)

    validation = out["analysis"]["market_validation"]
    assert validation["market_data_source"] == "failed"
    assert validation["market_data_present"] is False
    assert validation["A1"] <= 20
    assert out["execution"]["final"]["action"] != "EXECUTE"


def test_full_workflow_derives_market_input_from_payload_fields():
    payload = {
        "headline": "Fed action supports risk assets",
        "source": "https://example.com/news-2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spx_move_pct": 1.1,
        "vix_change_pct": -4.5,
        "sector_move_pct": 2.2,
    }

    out = FullWorkflowRunner().run(payload)
    validation = out["analysis"]["market_validation"]

    assert validation["market_data_source"] == "payload_derived"
    assert validation["market_data_present"] is True
