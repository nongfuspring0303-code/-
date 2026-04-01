import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ai_event_intel import NewsIngestion, EventEvidenceScorer
from edt_module_base import ModuleStatus


def test_news_ingestion_override():
    items = [
        {
            "headline": "Fed announces policy update",
            "source_url": "https://www.federalreserve.gov/",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_text": "policy update",
            "source_type": "official",
        }
    ]
    out = NewsIngestion().run({"items_override": items, "max_items": 1})
    assert out.status == ModuleStatus.SUCCESS
    assert len(out.data["items"]) == 1
    assert out.data["items"][0]["trace_id"]


def test_event_evidence_scorer_basic():
    payload = {
        "trace_id": "TRC-TEST-0001",
        "event_id": "ME-C-20260402-001.V1.0",
        "headline": "Fed announces policy update",
        "source_url": "https://www.federalreserve.gov/",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_text": "policy update",
        "source_type": "official",
        "schema_version": "ai_intel_v1",
        "producer": "member-a",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out = EventEvidenceScorer().run(payload)
    assert out.status == ModuleStatus.SUCCESS
    assert out.data["evidence_score"] >= 80
    assert out.data["confidence"] >= 0


def test_news_ingestion_timestamp_normalize_and_dedupe():
    items = [
        {
            "headline": "Gold dips on Fed focus",
            "source_url": "https://example.com/a",
            "timestamp": "Mon, 27 Jan 2025 14:26:00 -0500",
            "raw_text": "gold down",
            "source_type": "rss",
        },
        {
            "headline": "Gold dips on Fed focus",
            "source_url": "https://example.com/a",
            "timestamp": "Mon, 27 Jan 2025 14:40:00 -0500",
            "raw_text": "gold down again",
            "source_type": "rss",
        },
    ]
    out = NewsIngestion().run({"items_override": items, "max_items": 10})
    assert out.status == ModuleStatus.SUCCESS
    assert len(out.data["items"]) == 1
    ts = out.data["items"][0]["timestamp"]
    assert ts.endswith("Z")
    datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_event_evidence_scorer_abnormal_penalty():
    payload = {
        "trace_id": "TRC-TEST-0002",
        "event_id": "",
        "headline": "Rumor",
        "source_url": "https://pastebin.com/raw/abc",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_text": "rumor",
        "source_type": "unknown",
        "schema_version": "ai_intel_v1",
        "producer": "member-a",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out = EventEvidenceScorer().run(payload)
    assert out.status == ModuleStatus.SUCCESS
    assert out.data["evidence_score"] <= 30
