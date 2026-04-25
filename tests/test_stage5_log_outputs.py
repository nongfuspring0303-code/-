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
    assert "A_audit_completeness" in latest["owner_dimensions"]
    assert "B_output_quality" in latest["owner_dimensions"]
    assert "C_provider_freshness" in latest["owner_dimensions"]
    assert "final_reason" in latest
    assert isinstance(latest["theme_tags"], list)
    assert isinstance(latest["a_gate_blocker_codes"], list)
    assert isinstance(latest["a_gate_blocker_count"], int)
    assert isinstance(latest["a_gate_blocker_present"], bool)
    assert isinstance(latest["a_score_cap_applied"], bool)
    assert isinstance(latest["a_gate_signoff_ready"], bool)
    assert "mapping_source" in latest
    assert "placeholder_count" in latest
    assert "non_whitelist_sector_count" in latest
    assert "ticker_truth_source_hit" in latest
    assert "ticker_truth_source_miss" in latest
    assert "sector_quality_score" in latest
    assert "ticker_quality_score" in latest
    assert "output_quality_score" in latest
    assert "mapping_acceptance_score" in latest
    assert "b_overall_score" in latest
    assert isinstance(latest["b_signoff_ready"], bool)

    provider_daily = logs_dir / "provider_health_hourly.json"
    system_daily = logs_dir / "system_health_daily.json"
    report_daily = logs_dir / "system_health_daily_report.md"
    assert provider_daily.exists()
    assert system_daily.exists()
    assert report_daily.exists()


def test_stage5_scorecard_persists_semantic_contract_fields(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))

    monkeypatch.setattr(
        runner.semantic,
        "analyze",
        lambda _headline, _summary: {
            "event_type": "other",
            "sentiment": "negative",
            "confidence": 80,
            "recommended_chain": "trade_chain",
            "recommended_stocks": ["XLE", "CVX"],
            "a0_event_strength": 75,
            "expectation_gap": 15,
            "transmission_candidates": ["XLE", "USO", "CVX"],
            "fallback_reason": "",
        },
    )

    monkeypatch.setattr(
        runner.semantic,
        "analyze_event",
        lambda _headline, _summary, **_kwargs: {
            "event_type": "other",
            "event_time": "2026-04-25T00:00:00Z",
            "evidence_grade": "B",
        },
    )

    out = runner.run(_base_payload())
    execution_in = out["execution"]["input"]
    assert execution_in["recommended_chain"] == "trade_chain"
    assert execution_in["recommended_stocks"] == ["XLE", "CVX"]
    assert execution_in["transmission_candidates"] == ["XLE", "USO", "CVX"]

    score_rows = _read_jsonl(logs_dir / "trace_scorecard.jsonl")
    assert score_rows
    latest = score_rows[-1]
    assert latest["ai_sentiment"] == "negative"
    assert latest["ai_confidence"] == 80
    assert latest["ai_recommended_chain"] == "trade_chain"
    assert latest["ai_recommended_stocks"] == ["XLE", "CVX"]
    assert latest["ai_a0_event_strength"] == 75
    assert latest["ai_expectation_gap"] == 15
    assert latest["ai_transmission_candidates"] == ["XLE", "USO", "CVX"]
    assert latest["semantic_fallback_reason"] == ""
    assert latest["ai_missing_fields"] == []
    assert latest["semantic_defaults_applied"] is False


def test_stage5_scorecard_marks_semantic_missing_fields_from_raw_output(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))

    monkeypatch.setattr(
        runner.semantic,
        "analyze",
        lambda _headline, _summary: {
            "event_type": "other",
            "sentiment": "neutral",
            "confidence": 82,
            # intentionally missing:
            # - recommended_chain
            # - recommended_stocks
            # - expectation_gap
            # - transmission_candidates
        },
    )
    monkeypatch.setattr(
        runner.semantic,
        "analyze_event",
        lambda _headline, _summary, **_kwargs: {
            "event_type": "other",
            "event_time": "2026-04-25T00:00:00Z",
            "evidence_grade": "B",
        },
    )

    out = runner.run(_base_payload())
    execution_in = out["execution"]["input"]
    assert execution_in["recommended_chain"] == ""
    assert execution_in["recommended_stocks"] == []
    assert execution_in["expectation_gap"] == 0
    assert execution_in["transmission_candidates"] == []
    assert execution_in["semantic_defaults_applied"] is True
    assert set(execution_in["semantic_missing_fields"]) >= {
        "recommended_chain",
        "recommended_stocks",
        "expectation_gap",
        "transmission_candidates",
    }

    score_rows = _read_jsonl(logs_dir / "trace_scorecard.jsonl")
    latest = score_rows[-1]
    assert latest["semantic_defaults_applied"] is True
    assert set(latest["ai_missing_fields"]) >= {
        "recommended_chain",
        "recommended_stocks",
        "expectation_gap",
        "transmission_candidates",
    }


def test_stage5_market_provenance_includes_provider_failure_metadata(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(tmp_path / "state.db"))

    # Force adapter to produce provider failure metadata deterministically.
    monkeypatch.setattr(runner.opportunity._market_data_adapter, "_fetch_yahoo", lambda _symbols: {})
    monkeypatch.setattr(runner.opportunity._market_data_adapter, "_fetch_stooq", lambda _symbols: {})

    _ = runner.run(_base_payload())
    records = _read_jsonl(logs_dir / "market_data_provenance.jsonl")
    assert records
    uniqueness_keys = {
        (
            str(row.get("trace_id", "")),
            str(row.get("request_id", "")),
            str(row.get("batch_id", "")),
            str(row.get("event_hash", "")),
        )
        for row in records
    }
    assert len(uniqueness_keys) == len(records), "market_data_provenance should not duplicate the same trace tuple"
    enriched = [
        row
        for row in records
        if "providers_attempted" in row or "provider_failure_reasons" in row
    ]
    assert enriched, "expected at least one enriched provider provenance row"
    latest = enriched[-1]
    assert isinstance(latest.get("provider_chain", []), list)
    assert isinstance(latest.get("providers_attempted", []), list)
    assert isinstance(latest.get("providers_succeeded", []), list)
    assert isinstance(latest.get("providers_failed", []), list)
    assert isinstance(latest.get("provider_failure_reasons", {}), dict)
    assert isinstance(latest.get("fallback_reason", ""), str)
    assert isinstance(latest.get("unresolved_symbols", []), list)


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
    assert q["stage"] == "execution"
    assert q["reject_reason_code"]
    assert q["reject_reason_text"]
    assert q["ingest_ts"]
    assert q["decision_ts"]

    score_rows = _read_jsonl(logs_dir / "trace_scorecard.jsonl")
    latest_score = score_rows[-1]
    assert latest_score["a_gate_blocker_present"] is True
    assert "MARKET_DATA_DEFAULT_USED" in latest_score["a_gate_blocker_codes"]
    assert latest_score["scores"]["total_score"] <= 54.0
