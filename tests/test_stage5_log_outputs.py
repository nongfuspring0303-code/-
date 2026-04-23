import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def _base_payload() -> dict:
    return {
        "request_id": "REQ-S5-LOG-001",
        "batch_id": "BATCH-S5-LOG-001",
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


def test_stage5_pipeline_stage_and_scorecard_written(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))
    out = runner.run(_base_payload())

    trace_id = out["execution"]["trace_id"]
    pipeline_rows = _read_jsonl(logs_dir / "pipeline_stage.jsonl")
    score_rows = _read_jsonl(logs_dir / "trace_scorecard.jsonl")

    assert pipeline_rows, "pipeline_stage.jsonl should not be empty"
    assert score_rows, "trace_scorecard.jsonl should not be empty"

    stages = {row["stage"] for row in pipeline_rows if row.get("trace_id") == trace_id}
    expected = {
        "intel_ingest",
        "lifecycle",
        "fatigue",
        "conduction",
        "market_validation",
        "semantic",
        "path_adjudication",
        "signal",
        "opportunity",
        "execution",
    }
    assert expected.issubset(stages)

    latest = score_rows[-1]
    assert latest["trace_id"] == trace_id
    assert latest["event_hash"]
    assert latest["scores"]["total_score"] >= 0
    assert latest["scores"]["grade"] in {"A", "B", "C", "D"}
    assert "A_gate_safety" in latest["owner_dimensions"]
    assert "B_output_quality" in latest["owner_dimensions"]
    assert "C_provider_freshness" in latest["owner_dimensions"]


def test_stage5_rejected_and_quarantine_written_for_non_execute(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))
    payload = _base_payload()
    payload.update(
        {
            "request_id": "REQ-S5-REJECT-001",
            "batch_id": "BATCH-S5-REJECT-001",
            "market_data_source": "default",
            "market_data_default_used": True,
            "market_data_stale": True,
            "spx_move_pct": 0.0,
            "sector_move_pct": 0.0,
        }
    )

    out = runner.run(payload)
    assert out["execution"]["final"]["action"] in {"WATCH", "BLOCK", "FORCE_CLOSE", "PENDING_CONFIRM"}

    rejected_rows = _read_jsonl(logs_dir / "rejected_events.jsonl")
    quarantine_rows = _read_jsonl(logs_dir / "quarantine_replay.jsonl")
    assert rejected_rows, "rejected_events.jsonl should not be empty on non-execute path"
    assert quarantine_rows, "quarantine_replay.jsonl should not be empty on non-execute path"

    rej = rejected_rows[-1]
    q = quarantine_rows[-1]
    for row in (rej, q):
        assert row["trace_id"]
        assert row["event_hash"]
        assert row["request_id"] == "REQ-S5-REJECT-001"
        assert row["batch_id"] == "BATCH-S5-REJECT-001"

    assert rej["stage"] == "execution"
    assert rej["reject_reason_code"]
    assert "final_action" in rej
    assert q["quarantine_reason_code"]
