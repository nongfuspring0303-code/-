import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from compute_same_trace_ai_duplicate_call_rate import compute_duplicate_rate
from compute_stage5_acceptance_metrics import compute_metrics


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_compute_stage5_acceptance_metrics_on_clean_window(tmp_path):
    logs_dir = tmp_path / "logs"
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "metrics": {
                    "p95_decision_latency": 3.0,
                    "same_trace_ai_duplicate_call_rate": 0.5,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _write_jsonl(
        logs_dir / "decision_gate.jsonl",
        [
            {
                "trace_id": "T1",
                "final_action": "WATCH",
                "final_reason": "ok",
                "ingest_ts": "2026-04-24T01:00:00Z",
                "decision_ts": "2026-04-24T01:00:01Z",
            },
            {
                "trace_id": "T2",
                "final_action": "EXECUTE",
                "final_reason": "good",
                "ingest_ts": "2026-04-24T01:00:00Z",
                "decision_ts": "2026-04-24T01:00:02Z",
            },
        ],
    )
    _write_jsonl(
        logs_dir / "replay_join_validation.jsonl",
        [
            {"replay_primary_key_complete": True, "orphan_replay_count": 0, "orphan_execution_count": 0},
            {"replay_primary_key_complete": True, "orphan_replay_count": 0, "orphan_execution_count": 0},
        ],
    )
    _write_jsonl(
        logs_dir / "trace_scorecard.jsonl",
        [
            {"placeholder_count": 0, "non_whitelist_sector_count": 0, "semantic_event_type": "other"},
            {"placeholder_count": 0, "non_whitelist_sector_count": 0, "semantic_event_type": "other"},
        ],
    )
    _write_jsonl(
        logs_dir / "raw_news_ingest.jsonl",
        [
            {"trace_id": "T1"},
            {"trace_id": "T2"},
        ],
    )

    report = compute_metrics(logs_dir=logs_dir, baseline_path=baseline_path)
    metrics = report["metrics"]
    assert metrics["missing_opportunity_but_execute_count"] == 0
    assert metrics["market_data_default_used_in_execute_count"] == 0
    assert metrics["replay_primary_key_completeness"] == 1.0
    assert metrics["trace_join_success_rate"] == 1.0
    assert metrics["orphan_replay"] == 0
    assert report["baseline_compare"]["same_trace_ai_duplicate_call_rate_comparison"] == "improved_or_equal"


def test_compute_stage5_acceptance_metrics_prefers_structured_fields_over_reason_text(tmp_path):
    logs_dir = tmp_path / "logs"
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps({"metrics": {}}, ensure_ascii=False), encoding="utf-8")

    _write_jsonl(
        logs_dir / "decision_gate.jsonl",
        [
            # False-positive bait: reason mentions token, but structured fields are healthy.
            {
                "trace_id": "S1",
                "final_action": "EXECUTE",
                "final_reason": "note: missing_opportunity text in historical message",
                "has_opportunity": True,
                "opportunity_count": 2,
                "market_data_default_used": False,
            },
            # False-positive bait: reason mentions default-used token, but structured field says not used.
            {
                "trace_id": "S2",
                "final_action": "EXECUTE",
                "final_reason": "legacy marker market_data_default_used in copied comment",
                "has_opportunity": True,
                "opportunity_count": 1,
                "market_data_default_used": False,
            },
            # True positive: structured opportunity violation.
            {
                "trace_id": "S3",
                "final_action": "EXECUTE",
                "has_opportunity": False,
                "opportunity_count": 0,
                "market_data_default_used": False,
            },
            # True positive: structured default-used violation.
            {
                "trace_id": "S4",
                "final_action": "EXECUTE",
                "has_opportunity": True,
                "opportunity_count": 1,
                "market_data_default_used": True,
            },
        ],
    )
    _write_jsonl(logs_dir / "replay_join_validation.jsonl", [])
    _write_jsonl(logs_dir / "trace_scorecard.jsonl", [])
    _write_jsonl(logs_dir / "raw_news_ingest.jsonl", [])

    report = compute_metrics(logs_dir=logs_dir, baseline_path=baseline_path)
    metrics = report["metrics"]
    assert metrics["missing_opportunity_but_execute_count"] == 1
    assert metrics["market_data_default_used_in_execute_count"] == 1


def test_compute_duplicate_rate(tmp_path):
    logs_dir = tmp_path / "logs"
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"metrics": {"same_trace_ai_duplicate_call_rate": 0.5}}, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_jsonl(
        logs_dir / "raw_news_ingest.jsonl",
        [
            {"trace_id": "A"},
            {"trace_id": "A"},
            {"trace_id": "B"},
        ],
    )

    report = compute_duplicate_rate(logs_dir=logs_dir, baseline_path=baseline_path)
    assert report["duplicate_traces"] == 1
    assert report["total_traces"] == 2
    assert report["current_value"] == 0.5
    assert report["comparison"] == "improved_or_equal"
