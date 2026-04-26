import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner
from workflow_runner import WorkflowRunner


def _wait_for_non_empty_jsonl(path: Path, timeout_sec: float = 2.0) -> list[dict]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return [json.loads(line) for line in content.splitlines() if line.strip()]
        time.sleep(0.02)
    return []


def test_stage2_c_provenance_fields_persist_on_blocker_path(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))
    payload = {
        "request_id": "REQ-C-S2-PROV-001",
        "batch_id": "BATCH-C-S2-PROV-001",
        "headline": "Macro headline with stale market context",
        "source": "https://example.com/news",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_data_source": "failed",
        "market_data_stale": True,
        "spx_move_pct": 1.0,
        "vix_change_pct": -2.0,
        "sector_move_pct": 1.5,
    }

    out = runner.run(payload)
    assert out["execution"]["final"]["action"] != "EXECUTE"

    path = logs_dir / "market_data_provenance.jsonl"
    records = _wait_for_non_empty_jsonl(path)
    assert records, "market_data_provenance.jsonl should contain at least one record"
    rec = records[-1]
    assert rec["trace_id"]
    assert rec["event_trace_id"]
    assert rec["request_id"] == "REQ-C-S2-PROV-001"
    assert rec["batch_id"] == "BATCH-C-S2-PROV-001"
    assert rec["event_hash"]
    assert rec["market_data_source"] == "failed"
    assert rec["market_data_stale"] is True
    assert isinstance(rec["market_data_present"], bool)
    assert isinstance(rec["market_data_default_used"], bool)
    assert isinstance(rec["market_data_fallback_used"], bool)


def test_stage2_c_decision_gate_has_blocker_evidence(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s2_1.txt"),
        audit_dir=str(logs_dir),
    )
    payload = {
        "request_id": "REQ-C-S2-GATE-001",
        "batch_id": "BATCH-C-S2-GATE-001",
        "event_hash": "EVHASH-C-S2-001",
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
        "has_opportunity": False,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }

    out = runner.run(payload)
    assert out["final"]["action"] != "EXECUTE"

    records = _wait_for_non_empty_jsonl(logs_dir / "decision_gate.jsonl")
    assert records, "decision_gate.jsonl should contain blocker evidence"
    rec = records[-1]
    assert rec["request_id"] == "REQ-C-S2-GATE-001"
    assert rec["batch_id"] == "BATCH-C-S2-GATE-001"
    assert rec["event_hash"] == "EVHASH-C-S2-001"
    assert rec["final_action"] == out["final"]["action"]
    assert "missing_opportunity" in rec["output_gate"].get("blockers", [])


def test_stage2_c_provider_untrusted_is_blocked_by_output_gate(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s2_provider_untrusted.txt"),
        audit_dir=str(logs_dir),
    )
    payload = {
        "request_id": "REQ-C-S2-PROV-UNTRUSTED-001",
        "batch_id": "BATCH-C-S2-PROV-UNTRUSTED-001",
        "event_hash": "EVHASH-C-S2-PROV-UNTRUSTED-001",
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
        "has_opportunity": True,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
        "provider_untrusted": True,
    }

    out = runner.run(payload)
    assert out["final"]["action"] != "EXECUTE"

    records = _wait_for_non_empty_jsonl(logs_dir / "decision_gate.jsonl")
    assert records, "decision_gate.jsonl should contain provider_untrusted blocker evidence"
    rec = records[-1]
    assert rec["request_id"] == "REQ-C-S2-PROV-UNTRUSTED-001"
    assert rec["batch_id"] == "BATCH-C-S2-PROV-UNTRUSTED-001"
    assert rec["event_hash"] == "EVHASH-C-S2-PROV-UNTRUSTED-001"
    assert rec["final_action"] == out["final"]["action"]
    assert "provider_untrusted" in rec["output_gate"].get("blockers", [])


def test_stage2_c_blocker_path_no_execution_emit_and_replay_written(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s2_2.txt"),
        audit_dir=str(logs_dir),
    )
    payload = {
        "request_id": "REQ-C-S2-BLOCK-001",
        "batch_id": "BATCH-C-S2-BLOCK-001",
        "event_hash": "EVHASH-C-S2-002",
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
        "has_opportunity": True,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": True,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }

    out = runner.run(payload)
    assert out["final"]["action"] != "EXECUTE"

    emit_path = logs_dir / "execution_emit.jsonl"
    emit_content = emit_path.read_text(encoding="utf-8").strip() if emit_path.exists() else ""
    assert emit_content == ""

    replay_records = _wait_for_non_empty_jsonl(logs_dir / "replay_write.jsonl")
    assert replay_records, "replay_write.jsonl should keep blocker replay evidence"
    rec = replay_records[-1]
    assert rec["request_id"] == "REQ-C-S2-BLOCK-001"
    assert rec["batch_id"] == "BATCH-C-S2-BLOCK-001"
    assert rec["event_hash"] == "EVHASH-C-S2-002"
    assert rec["final_action"] == out["final"]["action"]


def test_stage2_c_replay_write_durable_before_run_return(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s2_3.txt"),
        audit_dir=str(logs_dir),
    )
    payload = {
        "request_id": "REQ-C-S2-DURABLE-001",
        "batch_id": "BATCH-C-S2-DURABLE-001",
        "event_hash": "EVHASH-C-S2-003",
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
        "has_opportunity": False,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }

    original_log_replay_task = runner._log_replay_task

    def delayed_log_replay_task(**kwargs):
        time.sleep(0.15)
        return original_log_replay_task(**kwargs)

    monkeypatch.setattr(runner, "_log_replay_task", delayed_log_replay_task)

    started_at = time.time()
    out = runner.run(payload)
    elapsed = time.time() - started_at

    assert out["final"]["action"] != "EXECUTE"
    # If replay writing is fire-and-forget, this read is often empty right after run() returns.
    replay_content = (logs_dir / "replay_write.jsonl").read_text(encoding="utf-8").strip()
    assert replay_content != ""
    replay_lines = [line for line in replay_content.splitlines() if line.strip()]
    assert len(replay_lines) == 1
    rec = json.loads(replay_lines[-1])
    assert rec["request_id"] == "REQ-C-S2-DURABLE-001"
    assert rec["batch_id"] == "BATCH-C-S2-DURABLE-001"
    assert rec["event_hash"] == "EVHASH-C-S2-003"
    assert rec["final_action"] == out["final"]["action"]
    assert elapsed >= 0.12
