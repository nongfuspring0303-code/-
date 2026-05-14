import sys
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner
from edt_module_base import ModuleOutput, ModuleStatus


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
        "theme_tags": ["macro_event", "liquidity_shock"],
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
    market_record = json.loads((logs_dir / "market_data_provenance.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
    gate_record = json.loads((logs_dir / "decision_gate.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
    replay_record = json.loads((logs_dir / "replay_write.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
    assert raw_record["trace_id"] == trace_id
    assert market_record["trace_id"] == trace_id
    assert gate_record["trace_id"] == trace_id
    assert replay_record["trace_id"] == trace_id
    assert raw_record["request_id"] == "REQ-EVIDENCE-001"
    assert gate_record["batch_id"] == "BATCH-EVIDENCE-001"
    assert replay_record["event_hash"] == raw_record["event_hash"]
    assert gate_record["event_hash"] == raw_record["event_hash"]
    assert market_record["event_hash"] == raw_record["event_hash"]

    assert gate_record["semantic_event_type"] in {"tariff", "geo_political", "earnings", "monetary", "energy", "shipping", "industrial", "tech", "healthcare", "regulatory", "merger", "inflation", "commodity", "credit", "natural_disaster", "pandemic", "other"}
    assert isinstance(gate_record["sector_candidates"], list)
    assert isinstance(gate_record["ticker_candidates"], list)
    assert gate_record["a1_score"] is not None
    assert gate_record["theme_tags"] == ["macro_event", "liquidity_shock"]
    assert gate_record["tradeable"] is not None
    assert isinstance(gate_record["opportunity_count"], int)

    emit_lines = (logs_dir / "execution_emit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    if out["execution"]["final"]["action"] == "EXECUTE":
        emit_record = json.loads(emit_lines[-1])
        assert emit_record["trace_id"] == trace_id
        assert emit_record["event_hash"] == raw_record["event_hash"]
    else:
        assert not emit_lines


def _base_payload_for_execution_suggestion():
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


def test_full_workflow_missing_score_does_not_silent_fallback():
    runner = FullWorkflowRunner()

    original_run = runner.scorer.run

    def _run_without_score(payload):
        out = original_run(payload)
        data = dict(out.data)
        data.pop("score", None)
        return SimpleNamespace(data=data)

    runner.scorer.run = _run_without_score
    out = runner.run(_base_payload_for_execution_suggestion())
    analysis = out["analysis"]
    assert "execution_suggestion" not in analysis
    assert analysis.get("execution_suggestion_status") == "failed"
    assert analysis.get("execution_suggestion_errors")


def test_full_workflow_missing_fatigue_score_uses_fatigue_final_fallback():
    runner = FullWorkflowRunner()

    original_run = runner.fatigue.run

    def _run_without_fatigue_score(payload):
        out = original_run(payload)
        data = dict(out.data)
        data.pop("fatigue_score", None)
        return SimpleNamespace(data=data)

    runner.fatigue.run = _run_without_fatigue_score
    out = runner.run(_base_payload_for_execution_suggestion())
    analysis = out["analysis"]
    assert "execution_suggestion" in analysis


def test_full_workflow_builder_failed_is_not_swallowed():
    runner = FullWorkflowRunner()

    def _force_failed(_payload):
        return ModuleOutput(
            status=ModuleStatus.FAILED,
            data={},
            errors=[{"code": "FORCED_FAILED", "message": "forced test failure"}],
        )

    runner.execution_suggestion_builder.run = _force_failed
    out = runner.run(_base_payload_for_execution_suggestion())
    analysis = out["analysis"]
    assert "execution_suggestion" not in analysis
    assert analysis.get("execution_suggestion_status") == "failed"
    assert analysis.get("execution_suggestion_errors") == [{"code": "FORCED_FAILED", "message": "forced test failure"}]


def test_full_workflow_path_quality_eval_failed_is_not_swallowed():
    runner = FullWorkflowRunner()

    def _force_failed(_payload):
        return ModuleOutput(
            status=ModuleStatus.FAILED,
            data={},
            errors=[{"code": "FORCED_FAILED_PQE", "message": "forced pqe failure"}],
        )

    runner.path_quality_evaluator.run = _force_failed
    out = runner.run(_base_payload_for_execution_suggestion())
    analysis = out["analysis"]
    assert "path_quality_eval" not in analysis
    assert analysis.get("path_quality_eval_status") == "failed"
    assert analysis.get("path_quality_eval_errors") == [{"code": "FORCED_FAILED_PQE", "message": "forced pqe failure"}]


def test_full_workflow_path_quality_eval_missing_upstream_does_not_inject_empty():
    """When upstream signals lack path_quality_eval inputs, the wiring must not inject empty dict."""
    runner = FullWorkflowRunner()

    original_run = runner.scorer.run

    def _run_without_pqe_fields(payload):
        out = original_run(payload)
        data = dict(out.data)
        # Remove fields that PathQualityEvaluator needs
        data.pop("relative_direction_score", None)
        data.pop("absolute_direction", None)
        data.pop("driver_confidence", None)
        data.pop("gap_score", None)
        data.pop("execution_confidence", None)
        return SimpleNamespace(data=data)

    runner.scorer.run = _run_without_pqe_fields
    out = runner.run(_base_payload_for_execution_suggestion())
    analysis = out["analysis"]
    # PathQualityEvaluator should FAIL because upstream inputs are missing
    assert "path_quality_eval" not in analysis
    assert analysis.get("path_quality_eval_status") == "failed"
    assert analysis.get("path_quality_eval_errors")


def test_full_workflow_path_quality_eval_success_path():
    """Verify that a valid payload correctly produces a path_quality_eval payload without failing."""
    runner = FullWorkflowRunner()

    # We need to mock upstream signals to ensure all fields required by PathQualityEvaluator are present
    original_run = runner.scorer.run
    
    def _run_with_perfect_pqe_fields(payload):
        out = original_run(payload)
        data = dict(out.data)
        data["score"] = 85.0  # Normalized to 0.85
        data["relative_direction_score"] = 0.9
        data["absolute_direction"] = "benefit"
        data["driver_confidence"] = 0.8
        data["gap_score"] = 0.7
        data["execution_confidence"] = 0.95
        return SimpleNamespace(data=data, status=ModuleStatus.SUCCESS)

    runner.scorer.run = _run_with_perfect_pqe_fields
    
    original_validation = runner.validation.run
    def _run_with_perfect_validation(payload):
        out = original_validation(payload)
        data = dict(out.data)
        data["checks"] = [
            {"status": "confirmed", "weight": 0.5},
            {"status": "partial", "weight": 0.5}
        ]
        return SimpleNamespace(data=data, status=ModuleStatus.SUCCESS)
        
    runner.validation.run = _run_with_perfect_validation

    out = runner.run(_base_payload_for_execution_suggestion())
    analysis = out["analysis"]
    
    # Must exist and be populated
    assert "path_quality_eval" in analysis
    assert "path_quality_eval_status" not in analysis or analysis["path_quality_eval_status"] != "failed"
    
    pqe = analysis["path_quality_eval"]
    assert "path_accuracy" in pqe
    assert "validation_accuracy" in pqe
    assert "direction_relative_accuracy" in pqe
    assert "direction_absolute_accuracy" in pqe
    assert "dominant_driver_accuracy" in pqe
    assert "expectation_gap_accuracy" in pqe
    assert "execution_decision_quality" in pqe
    assert "composite_score" in pqe
    assert "grade" in pqe
    
    # Check normalization
    assert pqe["path_accuracy"] == 0.85
    
    # Must not leak into execution
    assert "path_quality_eval" not in out["execution"]
