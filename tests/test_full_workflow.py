import sys
import json
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


def test_stage1_evidence_logs_written_with_trace_id(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))
    payload = {
        "request_id": "REQ-EVIDENCE-001",
        "batch_id": "BATCH-EVIDENCE-001",
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

    out = runner.run(payload)
    trace_id = out["execution"]["trace_id"]

    mandatory_files = [
        "raw_news_ingest.jsonl",
        "market_data_provenance.jsonl",
        "decision_gate.jsonl",
        "replay_write.jsonl",
        "execution_emit.jsonl",
    ]
    for name in mandatory_files:
        assert (logs_dir / name).exists(), name

    raw_record = json.loads((logs_dir / "raw_news_ingest.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
    gate_record = json.loads((logs_dir / "decision_gate.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
    replay_record = json.loads((logs_dir / "replay_write.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])

    assert raw_record["trace_id"] == trace_id
    assert gate_record["trace_id"] == trace_id
    assert replay_record["trace_id"] == trace_id
    assert raw_record["request_id"] == "REQ-EVIDENCE-001"
    assert gate_record["batch_id"] == "BATCH-EVIDENCE-001"
    assert replay_record["event_hash"] == raw_record["event_hash"]
    assert gate_record["event_hash"] == raw_record["event_hash"]

    emit_lines = (logs_dir / "execution_emit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    if out["execution"]["final"]["action"] == "EXECUTE":
        emit_record = json.loads(emit_lines[-1])
        assert emit_record["trace_id"] == trace_id
        assert emit_record["event_hash"] == raw_record["event_hash"]
