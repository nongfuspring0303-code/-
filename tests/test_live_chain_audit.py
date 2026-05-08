import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from live_chain_audit import _load_records, summarize_chain
from semantic_mapping_strict_report import build_strict_report


def _write_jsonl(path: Path, rows):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def _sample_rows():
    return [
        {
            "type": "event_update",
            "event_hash": "evt_hash_aaaaaaaaaaaaaaaa",
            "semantic_trace_id": "evt_live_aaaaaaaaaaaa",
            "trace_id": "evt_live_aaaaaaaaaaaa",
            "headline": "Fed officials still foresee rate cut",
            "schema_version": "v1.0",
        },
        {
            "type": "sector_update",
            "event_hash": "evt_hash_aaaaaaaaaaaaaaaa",
            "semantic_trace_id": "evt_live_aaaaaaaaaaaa",
            "trace_id": "evt_live_aaaaaaaaaaaa",
            "primary_sector": "科技",
            "sectors": [
                {"name": "科技", "direction": "LONG", "impact_score": 0.82, "confidence": 0.86, "role": "primary"},
                {"name": "金融", "direction": "SHORT", "impact_score": 0.75, "confidence": 0.8, "role": "secondary"},
            ],
            "schema_version": "v1.0",
        },
        {
            "type": "opportunity_update",
            "event_hash": "evt_hash_aaaaaaaaaaaaaaaa",
            "semantic_trace_id": "evt_live_aaaaaaaaaaaa",
            "trace_id": "evt_live_aaaaaaaaaaaa",
            "primary_sector": "科技",
            "audit_sectors": [{"name": "科技", "role": "primary"}, {"name": "金融", "role": "secondary"}],
            "opportunities": [{"symbol": "NVDA", "sector": "科技", "sector_role": "primary", "primary_sector": "科技", "signal": "LONG"}],
            "schema_version": "v1.0",
        },
    ]


def test_live_chain_audit_summary_from_fixture():
    records = _load_records(str(ROOT / "tests" / "fixtures" / "semantic_chain" / "sample_chain.jsonl"))
    summary = summarize_chain(records)

    assert summary["records_total"] == 3
    assert summary["type_counts"]["event_update"] == 1
    assert summary["type_counts"]["sector_update"] == 1
    assert summary["type_counts"]["opportunity_update"] == 1
    assert summary["event_hash_coverage"] == 1.0
    assert summary["semantic_trace_id_coverage"] == 1.0
    assert summary["missing_event_hash_count"] == 0
    assert summary["missing_semantic_trace_id_count"] == 0
    assert summary["parse_failed_count"] == 0
    assert summary["fallback_reason_distribution"] == {}
    assert summary["primary_sector_only"] is True
    assert summary["secondary_ticker_count"] == 0


def test_strict_report_happy_path_from_fixture():
    records = _load_records(str(ROOT / "tests" / "fixtures" / "semantic_chain" / "sample_chain.jsonl"))
    report = build_strict_report(records)

    assert report["summary"]["records_total"] == 3
    assert report["strict_join_ready_count"] == 1
    assert report["strict_join_failed_count"] == 0
    assert report["strict_join_ready_rate"] == 1.0
    assert report["secondary_ticker_count"] == 0
    assert report["fallback_pollution"] is False
    assert report["comparison_status"] == "observe_only"


def test_strict_report_detects_missing_event_hash(tmp_path):
    path = tmp_path / "missing_event_hash.jsonl"
    _write_jsonl(
        path,
        [
            {
                "type": "event_update",
                "semantic_trace_id": "evt_live_missing",
                "headline": "Missing event hash",
            },
            {
                "type": "sector_update",
                "event_hash": "evt_hash_missing",
                "semantic_trace_id": "evt_live_missing",
                "primary_sector": "科技",
                "sectors": [{"name": "科技", "role": "primary"}],
            },
            {
                "type": "opportunity_update",
                "event_hash": "evt_hash_missing",
                "semantic_trace_id": "evt_live_missing",
                "primary_sector": "科技",
                "opportunities": [],
            },
        ],
    )
    report = build_strict_report(_load_records(str(path)))
    assert report["missing_event_hash_count"] >= 1
    assert report["strict_join_ready_count"] == 0
    assert report["failure_reason_distribution"].get("missing_event_hash", 0) >= 1


def test_strict_report_detects_missing_semantic_trace_id(tmp_path):
    path = tmp_path / "missing_semantic_trace_id.jsonl"
    _write_jsonl(
        path,
        [
            {
                "type": "event_update",
                "event_hash": "evt_hash_missing_trace",
                "headline": "Missing semantic trace",
            },
            {
                "type": "sector_update",
                "event_hash": "evt_hash_missing_trace",
                "semantic_trace_id": "evt_live_missing_trace",
                "primary_sector": "科技",
                "sectors": [{"name": "科技", "role": "primary"}],
            },
            {
                "type": "opportunity_update",
                "event_hash": "evt_hash_missing_trace",
                "semantic_trace_id": "evt_live_missing_trace",
                "primary_sector": "科技",
                "opportunities": [],
            },
        ],
    )
    report = build_strict_report(_load_records(str(path)))
    assert report["missing_semantic_trace_id_count"] >= 1
    assert report["strict_join_ready_count"] == 0
    assert report["failure_reason_distribution"].get("missing_semantic_trace_id", 0) >= 1


def test_strict_report_detects_event_hash_mismatch(tmp_path):
    path = tmp_path / "event_hash_mismatch.jsonl"
    _write_jsonl(
        path,
        [
            {
                "type": "event_update",
                "event_hash": "evt_hash_a",
                "semantic_trace_id": "evt_live_shared",
                "headline": "Mismatch A",
            },
            {
                "type": "sector_update",
                "event_hash": "evt_hash_b",
                "semantic_trace_id": "evt_live_shared",
                "primary_sector": "科技",
                "sectors": [{"name": "科技", "role": "primary"}],
            },
            {
                "type": "opportunity_update",
                "event_hash": "evt_hash_b",
                "semantic_trace_id": "evt_live_shared",
                "primary_sector": "科技",
                "opportunities": [],
            },
        ],
    )
    report = build_strict_report(_load_records(str(path)))
    assert report["event_hash_mismatch_count"] >= 1
    assert report["strict_join_ready_count"] == 0
    assert report["failure_reason_distribution"].get("event_hash_mismatch", 0) >= 1


def test_strict_report_detects_opportunity_without_sector(tmp_path):
    path = tmp_path / "opportunity_without_sector.jsonl"
    _write_jsonl(
        path,
        [
            {
                "type": "event_update",
                "event_hash": "evt_hash_only",
                "semantic_trace_id": "evt_live_only",
                "headline": "Only event",
            },
            {
                "type": "opportunity_update",
                "event_hash": "evt_hash_only",
                "semantic_trace_id": "evt_live_only",
                "primary_sector": "科技",
                "opportunities": [],
            },
        ],
    )
    report = build_strict_report(_load_records(str(path)))
    assert report["opportunity_without_sector_count"] >= 1
    assert report["strict_join_ready_count"] == 0
    assert report["failure_reason_distribution"].get("opportunity_without_sector", 0) >= 1


def test_strict_report_detects_sector_without_event(tmp_path):
    path = tmp_path / "sector_without_event.jsonl"
    _write_jsonl(
        path,
        [
            {
                "type": "sector_update",
                "event_hash": "evt_hash_sector_only",
                "semantic_trace_id": "evt_live_sector_only",
                "primary_sector": "科技",
                "sectors": [{"name": "科技", "role": "primary"}],
            },
            {
                "type": "opportunity_update",
                "event_hash": "evt_hash_sector_only",
                "semantic_trace_id": "evt_live_sector_only",
                "primary_sector": "科技",
                "opportunities": [],
            },
        ],
    )
    report = build_strict_report(_load_records(str(path)))
    assert report["sector_without_event_count"] >= 1
    assert report["strict_join_ready_count"] == 0
    assert report["failure_reason_distribution"].get("sector_without_event", 0) >= 1


def test_strict_report_detects_duplicate_trace(tmp_path):
    path = tmp_path / "duplicate_trace.jsonl"
    _write_jsonl(
        path,
        [
            {
                "type": "event_update",
                "event_hash": "evt_hash_dup",
                "semantic_trace_id": "evt_live_dup",
                "headline": "Dup 1",
            },
            {
                "type": "event_update",
                "event_hash": "evt_hash_dup_2",
                "semantic_trace_id": "evt_live_dup",
                "headline": "Dup 2",
            },
            {
                "type": "sector_update",
                "event_hash": "evt_hash_dup",
                "semantic_trace_id": "evt_live_dup",
                "primary_sector": "科技",
                "sectors": [{"name": "科技", "role": "primary"}],
            },
            {
                "type": "opportunity_update",
                "event_hash": "evt_hash_dup",
                "semantic_trace_id": "evt_live_dup",
                "primary_sector": "科技",
                "opportunities": [],
            },
        ],
    )
    report = build_strict_report(_load_records(str(path)))
    assert report["duplicate_final_verdict_count"] >= 0
    assert report["strict_join_ready_count"] == 0
    assert report["failure_reason_distribution"].get("event_hash_mismatch", 0) >= 1


def test_live_chain_audit_cli_emits_json(capsys):
    source = ROOT / "tests" / "fixtures" / "semantic_chain" / "sample_chain.jsonl"
    from live_chain_audit import main

    exit_code = main(["--input", str(source)])

    assert exit_code == 0
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["records_total"] == 3


def test_semantic_chain_policy_uses_schema_version():
    import yaml

    policy = yaml.safe_load((ROOT / "configs" / "semantic_chain_policy.yaml").read_text(encoding="utf-8"))
    assert policy["schema_version"] == "semantic_chain_policy.v1"
