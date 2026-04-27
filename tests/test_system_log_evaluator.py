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
                "fallback_used": False,
                "providers_failed": ["yahoo"],
                "provider_failure_reasons": {"yahoo": "empty_response"},
                "fallback_reason": "NO_PRICE_RESOLVED",
                "unresolved_symbols": ["NVDA"],
            },
            {
                "logged_at": "2026-04-24T01:11:00Z",
                "market_data_source": "fallback",
                "market_data_present": True,
                "market_data_stale": False,
                "market_data_default_used": False,
                "market_data_fallback_used": True,
                "fallback_used": True,
                "providers_failed": [],
                "provider_failure_reasons": {},
                "fallback_reason": "",
                "unresolved_symbols": [],
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
    assert provider["market_fallback_used_count"] == 1
    assert provider["provider_fallback_used_count"] == 1
    assert provider["market_fallback_used_rate"] > 0
    assert provider["provider_fallback_used_rate"] > 0
    assert provider["provider_failed_count"] >= 1
    assert provider["unresolved_symbol_count"] >= 1
    assert provider["fallback_reason_counts"]["NO_PRICE_RESOLVED"] >= 1
    assert provider["provider_failure_reason_counts"]["yahoo:empty_response"] >= 1

    daily = out["system_health_daily"][0]
    assert daily["date_utc"] == "2026-04-24"
    assert daily["ingest_count"] == 2
    assert daily["quarantine_activity_monitor"]["alert"] == ""
    assert daily["quarantine_activity_monitor"]["hours_checked"] >= 1
    assert isinstance(daily["quarantine_activity_monitor"]["alert_hours_utc"], list)


def test_system_log_evaluator_quarantine_silent_alert_on_hourly_window(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        logs_dir / "raw_news_ingest.jsonl",
        [
            {"logged_at": "2026-04-24T01:05:00Z", "trace_id": "T1"},
            {"logged_at": "2026-04-24T02:05:00Z", "trace_id": "T2"},
        ],
    )
    _write_jsonl(
        logs_dir / "market_data_provenance.jsonl",
        [
            {
                "logged_at": "2026-04-24T01:06:00Z",
                "market_data_source": "payload_direct",
                "market_data_present": True,
                "market_data_stale": False,
                "market_data_default_used": False,
                "market_data_fallback_used": False,
                "fallback_used": False,
            }
        ],
    )
    _write_jsonl(logs_dir / "pipeline_stage.jsonl", [])
    _write_jsonl(logs_dir / "decision_gate.jsonl", [{"logged_at": "2026-04-24T02:06:00Z", "final_action": "WATCH"}])
    _write_jsonl(
        logs_dir / "rejected_events.jsonl",
        [{"logged_at": "2026-04-24T02:07:00Z", "trace_id": "T2", "reject_reason_code": "EXECUTION_GATE_REJECTED"}],
    )
    _write_jsonl(
        logs_dir / "quarantine_replay.jsonl",
        [{"logged_at": "2026-04-24T02:08:00Z", "trace_id": "T2", "reject_reason_code": "EXECUTION_GATE_REJECTED"}],
    )
    _write_jsonl(logs_dir / "trace_scorecard.jsonl", [])

    out = evaluate_logs(logs_dir=logs_dir, gate_enabled=True)
    daily = out["system_health_daily"][0]
    assert daily["quarantine_activity_monitor"]["alert"] == "QUARANTINE_SILENT_ALERT"
    assert "2026-04-24T01:00:00Z" in daily["quarantine_activity_monitor"]["alert_hours_utc"]


def test_system_log_evaluator_tracks_provider_fallback_separately_from_market_fallback(tmp_path):
    # Rule/Test mapping: R93-PROV-003 / T-R93-PROV-003 (evaluator-side)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        logs_dir / "market_data_provenance.jsonl",
        [
            {
                "logged_at": "2026-04-24T03:00:00Z",
                "market_data_source": "payload_direct",
                "market_data_present": True,
                "market_data_stale": False,
                "market_data_default_used": False,
                "market_data_fallback_used": False,
                # provider-level fallback happened (active failed, fallback provider succeeded)
                "fallback_used": True,
                "providers_failed": ["yahoo"],
                "provider_failure_reasons": {"yahoo": "empty_response"},
                "fallback_reason": "",
                "unresolved_symbols": [],
            }
        ],
    )

    out = evaluate_logs(logs_dir=logs_dir, gate_enabled=True)
    provider = out["provider_health_hourly"][0]
    assert provider["market_fallback_used_count"] == 0
    assert provider["market_fallback_used_rate"] == 0.0
    assert provider["provider_fallback_used_count"] == 1
    assert provider["provider_fallback_used_rate"] == 1.0
