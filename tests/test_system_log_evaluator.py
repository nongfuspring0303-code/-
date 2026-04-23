import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from system_log_evaluator import evaluate_logs


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_system_log_evaluator_generates_provider_and_daily_health(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        logs_dir / "raw_news_ingest.jsonl",
        [
            {"logged_at": "2026-04-24T01:00:00Z", "trace_id": "T1"},
            {"logged_at": "2026-04-24T01:10:00Z", "trace_id": "T2"},
        ],
    )
    _write_jsonl(
        logs_dir / "market_data_provenance.jsonl",
        [
            {
                "logged_at": "2026-04-24T01:01:00Z",
                "market_data_source": "payload_direct",
                "market_data_present": True,
                "market_data_stale": False,
                "market_data_default_used": False,
                "market_data_fallback_used": False,
            },
            {
                "logged_at": "2026-04-24T01:11:00Z",
                "market_data_source": "fallback",
                "market_data_present": True,
                "market_data_stale": False,
                "market_data_default_used": False,
                "market_data_fallback_used": True,
            },
        ],
    )
    _write_jsonl(
        logs_dir / "pipeline_stage.jsonl",
        [
            {"logged_at": "2026-04-24T01:00:00Z", "trace_id": "T1", "stage": s}
            for s in (
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
            )
        ],
    )
    _write_jsonl(
        logs_dir / "decision_gate.jsonl",
        [
            {"logged_at": "2026-04-24T01:02:00Z", "final_action": "EXECUTE"},
            {"logged_at": "2026-04-24T01:12:00Z", "final_action": "WATCH"},
        ],
    )
    _write_jsonl(
        logs_dir / "rejected_events.jsonl",
        [{"logged_at": "2026-04-24T01:12:30Z", "trace_id": "T2", "reject_reason_code": "EXECUTION_GATE_REJECTED"}],
    )
    _write_jsonl(
        logs_dir / "quarantine_replay.jsonl",
        [{"logged_at": "2026-04-24T01:12:40Z", "trace_id": "T2", "quarantine_reason_code": "EXECUTION_GATE_REJECTED"}],
    )
    _write_jsonl(
        logs_dir / "trace_scorecard.jsonl",
        [
            {"logged_at": "2026-04-24T01:02:10Z", "scores": {"total_score": 91.0}},
            {"logged_at": "2026-04-24T01:12:50Z", "scores": {"total_score": 73.0}},
        ],
    )

    out = evaluate_logs(logs_dir=logs_dir, gate_enabled=True)

    assert out["provider_health_hourly"], "provider_health_hourly should be generated"
    assert out["system_health_daily"], "system_health_daily should be generated"
    assert "Stage5 Daily Health Report" in out["daily_report_markdown"]

    provider = out["provider_health_hourly"][0]
    assert provider["hour_bucket_utc"].startswith("2026-04-24T01:")
    assert provider["fallback_used_rate"] > 0

    daily = out["system_health_daily"][0]
    assert daily["date_utc"] == "2026-04-24"
    assert daily["ingest_count"] == 2
    assert daily["quarantine_activity_monitor"]["alert"] == ""
