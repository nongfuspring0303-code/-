import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner
from multi_event_arbiter import MultiEventArbiter
from workflow_runner import WorkflowRunner


def _stage4_payload() -> dict:
    return {
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


def _execution_payload(request_id: str, batch_id: str, event_hash: str) -> dict:
    return {
        "request_id": request_id,
        "batch_id": batch_id,
        "event_hash": event_hash,
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
        "symbol": "SPY",
        "has_opportunity": True,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }


def test_dual_write_backward_compat_test(tmp_path):
    # Test ID: T-S4-007 -> Rule ID: R-S4-DUAL-WRITE
    runner = FullWorkflowRunner(audit_dir=str(tmp_path / "logs"), state_db_path=str(tmp_path / "state.db"))
    out = runner.run(_stage4_payload())

    contract_meta = out["analysis"]["contract_meta"]
    execution_in = out["execution"]["input"]

    assert contract_meta["dual_write"] is True
    assert contract_meta["contract_version"] == "v2.2"
    assert contract_meta["legacy_contract_version"] == "v1.0"
    assert execution_in["dual_write"] is True
    assert execution_in["contract_version"] == "v2.2"
    assert execution_in["legacy_contract_version"] == "v1.0"


def test_priority_queue_order_semantics_test(monkeypatch):
    # Test ID: T-S4-008 -> Rule ID: R-S4-QUEUE-ORDER
    arbiter = MultiEventArbiter()
    processed_order = []

    def fake_run(payload):
        processed_order.append(payload["request_id"])
        return {"execution": {"final": {"action": "WATCH", "score": 0, "position_notional": 0}}}

    monkeypatch.setattr(arbiter.runner, "run", fake_run)

    events = [
        {
            "headline": "low severity",
            "source": "https://example.com/low",
            "timestamp": "2026-04-24T00:00:00+00:00",
            "symbol": "LOW",
            "severity": "E2",
            "request_id": "REQ-LOW",
        },
        {
            "headline": "high severity",
            "source": "https://example.com/high",
            "timestamp": "2026-04-24T00:00:01+00:00",
            "symbol": "HIGH",
            "severity": "E4",
            "request_id": "REQ-HIGH",
        },
        {
            "headline": "middle severity",
            "source": "https://example.com/mid",
            "timestamp": "2026-04-24T00:00:02+00:00",
            "symbol": "MID",
            "severity": "E3",
            "request_id": "REQ-MID",
        },
    ]

    out = arbiter.run_batch(events)
    assert out["processed"] == 3
    assert processed_order == ["REQ-HIGH", "REQ-MID", "REQ-LOW"]


def test_idempotent_replay_write_test(tmp_path):
    # Test ID: T-S4-009 -> Rule ID: R-S4-IDEMPOTENT-REPLAY
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_stage4.txt"),
        audit_dir=str(logs_dir),
    )

    payload = _execution_payload(
        request_id="REQ-S4-IDEMP-001",
        batch_id="BATCH-S4-IDEMP-001",
        event_hash="EVHASH-S4-IDEMP-001",
    )

    first = runner.run(payload)
    assert first["final"]["action"] == "EXECUTE"

    replay_path = logs_dir / "replay_write.jsonl"
    before = replay_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(before) >= 1

    second = runner.run(payload)
    assert second["final"]["action"] == "DUPLICATE_IGNORED"

    after = replay_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(after) == len(before)

    latest = json.loads(after[-1])
    assert latest["request_id"] == "REQ-S4-IDEMP-001"
