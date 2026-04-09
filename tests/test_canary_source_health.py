import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import canary_source_health as csh
from canary_source_health import CanarySourceHealth


def test_canary_source_health_collects_and_summarizes(tmp_path, monkeypatch):
    def fake_collect(self, source_url, timeout, max_items):
        return "success", [
            {
                "headline": "Fed signals policy shift",
                "source_url": source_url,
                "timestamp": "2026-04-10T01:02:03Z",
                "source_type": "rss",
            }
        ], None

    monkeypatch.setattr(CanarySourceHealth, "_collect_feed_items", fake_collect)
    health = CanarySourceHealth(audit_dir=str(tmp_path))
    record = health.collect_once()

    assert record["is_canary"] is True
    assert record["fetch_status"] == "success"
    assert record["source_id"] == "reuters_rss_top_news"
    assert record["new_item_count"] == 1
    assert record["items"][0]["trace_id"].startswith(record["trace_id"])
    assert (tmp_path / "canary_health.jsonl").exists()
    assert (tmp_path / "canary_health_summary.json").exists()
    assert (tmp_path / "canary_health_report.json").exists()

    summary = health.read_summary()
    assert summary["source_id"] == "reuters_rss_top_news"
    assert summary["windows"]["60"]["success_rate"] == 1.0
    assert summary["windows"]["60"]["new_item_count"] == 1
    assessment = health.assess(summary=summary, mode="prod")
    assert assessment.status == "GREEN"


def test_canary_source_health_yellow_without_samples(tmp_path):
    health = CanarySourceHealth(audit_dir=str(tmp_path))
    summary = health.read_summary()
    assessment = health.assess(summary=summary, mode="dev")
    assert assessment.status == "YELLOW"
    assert "No live canary samples" in assessment.summary

