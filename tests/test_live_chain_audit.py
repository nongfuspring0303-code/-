import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from live_chain_audit import _load_records, summarize_chain
from semantic_mapping_strict_report import build_strict_report


def test_live_chain_audit_summary_from_fixture():
    records = _load_records(str(ROOT / "tests" / "fixtures" / "semantic_chain" / "sample_chain.jsonl"))
    summary = summarize_chain(records)

    assert summary["records_total"] == 3
    assert summary["type_counts"]["event_update"] == 1
    assert summary["type_counts"]["sector_update"] == 1
    assert summary["type_counts"]["opportunity_update"] == 1
    assert summary["event_hash_coverage"] == 1.0
    assert summary["semantic_trace_id_coverage"] == 1.0
    assert summary["primary_sector_only"] is True
    assert summary["secondary_ticker_count"] == 0


def test_strict_report_marks_identity_and_secondary_audit_visibility():
    records = _load_records(str(ROOT / "tests" / "fixtures" / "semantic_chain" / "sample_chain.jsonl"))
    report = build_strict_report(records)

    assert report["summary"]["records_total"] == 3
    assert report["strict_join_ready_count"] == 1
    assert report["strict_join_ready_rate"] == 1.0
    assert report["secondary_ticker_count"] == 0
    assert report["fallback_pollution"] is False
    assert report["comparison_status"] == "observe_only"


def test_live_chain_audit_cli_emits_json(tmp_path, monkeypatch, capsys):
    source = ROOT / "tests" / "fixtures" / "semantic_chain" / "sample_chain.jsonl"
    from live_chain_audit import main

    exit_code = main(["--input", str(source)])

    assert exit_code == 0
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["records_total"] == 3
    assert payload["event_hash_coverage"] == 1.0
