import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner
from system_log_evaluator import evaluate_logs
from workflow_runner import WorkflowRunner


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _base_execution_payload(request_id: str, batch_id: str, event_hash: str) -> dict:
    return {
        "request_id": request_id,
        "batch_id": batch_id,
        "event_hash": event_hash,
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
    }


def test_residual_market_data_provenance_fields_are_extended_and_missing_tracked(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))
    payload = {
        "request_id": "REQ-RESIDUAL-PROV-001",
        "batch_id": "BATCH-RESIDUAL-PROV-001",
        "headline": "Residual provenance contract extension check",
        "source": "https://example.com/news",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_data_source": "failed",
        "market_data_stale": True,
    }

    runner.run(payload)
    rows = _read_jsonl(logs_dir / "market_data_provenance.jsonl")
    assert rows
    rec = rows[-1]

    for field in (
        "market_data_provider",
        "provider_path",
        "symbols_requested",
        "symbols_returned",
        "request_mode",
        "fetch_latency_ms",
        "market_data_ts",
        "market_data_delay_seconds",
        "rate_limited",
        "http_status",
        "error_code",
        "used_by_module",
        "provenance_field_missing",
    ):
        assert field in rec
    assert rec["used_by_module"] == "MarketValidator"
    assert rec["market_data_provider"] is None
    assert rec["provider_path"] is None
    assert rec["symbols_requested"] == []
    assert rec["symbols_returned"] == []
    assert isinstance(rec["provenance_field_missing"], list)
    assert "market_data_provider" in rec["provenance_field_missing"]
    assert "provider_path" in rec["provenance_field_missing"]


def test_residual_market_data_provenance_prefers_payload_symbols_and_metadata(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))
    payload = {
        "request_id": "REQ-RESIDUAL-PROV-PASS-001",
        "batch_id": "BATCH-RESIDUAL-PROV-PASS-001",
        "headline": "Residual provenance positive-path check",
        "source": "https://example.com/news",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_data_source": "payload_direct",
        "market_data_provider": "yahoo_finance",
        "provider_path": "yahoo_http",
        "symbols_requested": ["spy", "xle", "SPY"],
        "symbols_returned": ["spy", "xle"],
        "request_mode": "realtime",
        "fetch_latency_ms": 84,
        "http_status": 200,
    }

    runner.run(payload)
    rows = _read_jsonl(logs_dir / "market_data_provenance.jsonl")
    assert rows
    rec = rows[-1]
    assert rec["market_data_provider"] == "yahoo_finance"
    assert rec["provider_path"] == "yahoo_http"
    assert rec["symbols_requested"] == ["SPY", "XLE"]
    assert rec["symbols_returned"] == ["SPY", "XLE"]
    assert rec["request_mode"] == "realtime"
    assert rec["fetch_latency_ms"] == 84
    assert rec["http_status"] == 200
    assert "symbols_requested" not in rec["provenance_field_missing"]
    assert "symbols_returned" not in rec["provenance_field_missing"]


def test_residual_decision_gate_prepost_and_hard_rules_are_structured(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_residual.txt"),
        audit_dir=str(logs_dir),
    )
    scenarios = [
        (
            "missing_opportunity",
            {"has_opportunity": False},
            "MISSING_OPPORTUNITY",
        ),
        (
            "market_data_default_used",
            {"market_data_default_used": True},
            "MARKET_DATA_DEFAULT_USED",
        ),
        (
            "tradeable_false",
            {"tradeable": False},
            "TRADEABLE_FALSE",
        ),
    ]

    for idx, (rule_name, overrides, expected_reject_code) in enumerate(scenarios, start=1):
        payload = _base_execution_payload(
            request_id=f"REQ-RESIDUAL-GATE-{idx:03d}",
            batch_id=f"BATCH-RESIDUAL-GATE-{idx:03d}",
            event_hash=f"EVHASH-RESIDUAL-GATE-{idx:03d}",
        )
        payload.update(overrides)
        out = runner.run(payload)
        assert out["final"]["action"] != "EXECUTE", f"{rule_name} must not execute"

    gate_rows = _read_jsonl(logs_dir / "decision_gate.jsonl")
    assert len(gate_rows) >= len(scenarios)
    tail_rows = gate_rows[-len(scenarios):]
    expected_codes = [x[2] for x in scenarios]
    for rec, expected_code in zip(tail_rows, expected_codes):
        assert rec["final_action_before_gate"] == "EXECUTE"
        assert rec["final_action_after_gate"] in {"WATCH", "BLOCK", "PENDING_CONFIRM"}
        assert rec["gate_result"] in {"WATCH", "BLOCK", "PENDING_CONFIRM"}
        assert isinstance(rec["triggered_rules"], list)
        assert rec["reject_reason_code"] == expected_code
        assert isinstance(rec["reject_reason_text"], str) and rec["reject_reason_text"]


def test_residual_decision_gate_execute_path_is_pass_with_null_reject_fields(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_residual_execute.txt"),
        audit_dir=str(logs_dir),
    )
    payload = _base_execution_payload(
        request_id="REQ-RESIDUAL-GATE-PASS-001",
        batch_id="BATCH-RESIDUAL-GATE-PASS-001",
        event_hash="EVHASH-RESIDUAL-GATE-PASS-001",
    )

    out = runner.run(payload)
    assert out["final"]["action"] == "EXECUTE"

    gate_rows = _read_jsonl(logs_dir / "decision_gate.jsonl")
    assert gate_rows
    rec = gate_rows[-1]
    assert rec["final_action_after_gate"] == "EXECUTE"
    assert rec["gate_result"] == "PASS"
    assert rec["reject_reason_code"] is None
    assert rec["reject_reason_text"] is None


def test_residual_evaluator_replay_execution_health_detects_missing_links(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    day = "2026-04-25"
    _write_jsonl(logs_dir / "raw_news_ingest.jsonl", [{"logged_at": f"{day}T01:00:00Z", "trace_id": "T0"}])
    _write_jsonl(logs_dir / "market_data_provenance.jsonl", [{"logged_at": f"{day}T01:00:01Z"}])
    _write_jsonl(logs_dir / "pipeline_stage.jsonl", [])
    _write_jsonl(
        logs_dir / "decision_gate.jsonl",
        [{"logged_at": f"{day}T01:00:02Z", "trace_id": "T1", "event_hash": "H1", "final_action": "EXECUTE"}],
    )
    _write_jsonl(logs_dir / "rejected_events.jsonl", [])
    _write_jsonl(logs_dir / "quarantine_replay.jsonl", [])
    _write_jsonl(logs_dir / "trace_scorecard.jsonl", [{"logged_at": f"{day}T01:00:03Z", "scores": {"total_score": 80}}])
    _write_jsonl(
        logs_dir / "replay_write.jsonl",
        [
            {"logged_at": f"{day}T01:00:10Z", "trace_id": "T1", "event_hash": "H1"},
            {"logged_at": f"{day}T01:00:11Z", "trace_id": "T3", "event_hash": "H3"},
        ],
    )
    _write_jsonl(
        logs_dir / "execution_emit.jsonl",
        [
            {"logged_at": f"{day}T01:00:20Z", "trace_id": "T1", "event_hash": "H1"},
            {"logged_at": f"{day}T01:00:21Z", "trace_id": "T2", "event_hash": "H2"},
        ],
    )

    out = evaluate_logs(logs_dir=logs_dir, gate_enabled=True)
    assert out["system_health_daily"]
    daily = out["system_health_daily"][0]
    assert "replay_execution_health" in daily
    replay_health = daily["replay_execution_health"]
    assert replay_health["replay_write_count"] == 2
    assert replay_health["execution_emit_count"] == 2
    assert replay_health["orphan_replay_count"] == 1
    assert replay_health["execute_without_replay_count"] == 1
    assert replay_health["execute_without_gate_count"] == 1
    assert 0.0 <= replay_health["replay_execution_separation_rate"] <= 1.0


def test_residual_tighten_missing_and_reject_code(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))

    # 1. provider-call 字段为空字符串或空白字符串 -> missing
    payload_missing = {
        "request_id": "REQ-RESIDUAL-TIGHTEN-001",
        "batch_id": "BATCH-RESIDUAL-TIGHTEN-001",
        "headline": "Tighten missing check",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_data_provider": "  ",  # blank string
        "provider_path": "",  # empty string
    }
    runner.run(payload_missing)
    rows = _read_jsonl(logs_dir / "market_data_provenance.jsonl")
    rec = rows[-1]
    assert "market_data_provider" in rec["provenance_field_missing"]
    assert "provider_path" in rec["provenance_field_missing"]

    # 2. market_data_missing blocker -> MARKET_DATA_MISSING reject code
    wr = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_residual_tighten.txt"),
        audit_dir=str(logs_dir),
    )
    payload_gate = _base_execution_payload(
        request_id="REQ-RESIDUAL-TIGHTEN-002",
        batch_id="BATCH-RESIDUAL-TIGHTEN-002",
        event_hash="EVHASH-RESIDUAL-TIGHTEN-002",
    )
    payload_gate.update({"market_data_present": False})
    wr.run(payload_gate)
    gate_rows = _read_jsonl(logs_dir / "decision_gate.jsonl")
    gate_rec = gate_rows[-1]
    assert "market_data_missing" in gate_rec["triggered_rules"]
    assert gate_rec["reject_reason_code"] == "MARKET_DATA_MISSING"
