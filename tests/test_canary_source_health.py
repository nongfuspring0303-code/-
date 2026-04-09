import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import canary_source_health as csh
from canary_source_health import CanarySourceHealth


def test_canary_source_health_falls_back_to_backup_source(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(self, source_spec, timeout, max_items):
        source_url = source_spec["url"] if isinstance(source_spec, dict) else source_spec
        calls.append(source_url)
        if "reutersagency.com" in source_url:
            return {
                "status": "failed",
                "items": [],
                "error": "network_error",
                "fetch_latency_ms": 12.5,
            }
        return {
            "status": "success",
            "items": [
                {
                    "headline": "Fed signals policy shift",
                    "source_url": source_url,
                    "timestamp": "2026-04-10T01:02:03Z",
                    "source_type": "rss",
                }
            ],
            "error": None,
            "fetch_latency_ms": 21.5,
        }

    monkeypatch.setattr(CanarySourceHealth, "_fetch_source_once", fake_fetch)
    monkeypatch.setattr(csh.time, "sleep", lambda *_args, **_kwargs: None)
    health = CanarySourceHealth(audit_dir=str(tmp_path))
    health.sources = [
        {"url": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best", "kind": "rss"},
        {"url": "https://www.reuters.com/markets/rss", "kind": "rss"},
        {"url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&hl=en-US&gl=US&ceid=US:en", "kind": "rss"},
    ]
    record = health.collect_once()

    assert record["is_canary"] is True
    assert record["fetch_status"] == "success"
    assert record["source_id"] == "newsapi_us_top_headlines"
    assert record["new_item_count"] == 1
    assert record["source_url"] == "https://www.reuters.com/markets/rss"
    assert record["primary_source_url"] == "https://newsapi.org/v2/top-headlines?country=us"
    assert len(record["attempted_sources"]) == 2
    assert calls[0] == "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"
    assert calls[1] == "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"
    assert calls[2] == "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"
    assert calls[3] == "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"
    assert calls[4] == "https://www.reuters.com/markets/rss"
    assert record["items"][0]["trace_id"].startswith(record["trace_id"])
    assert (tmp_path / "canary_health.jsonl").exists()
    assert (tmp_path / "canary_health_summary.json").exists()
    assert (tmp_path / "canary_health_report.json").exists()

    summary = health.read_summary()
    assert summary["source_id"] == "newsapi_us_top_headlines"
    assert summary["windows"]["60"]["success_rate"] == 1.0
    assert summary["windows"]["60"]["new_item_count"] == 1
    assessment = health.assess(summary=summary, mode="prod")
    assert assessment.status == "GREEN"


def test_canary_source_health_parses_newsapi_payload(tmp_path):
    health = CanarySourceHealth(audit_dir=str(tmp_path))
    payload = json.dumps(
        {
            "status": "ok",
            "articles": [
                {
                    "title": "Fed signals policy shift",
                    "url": "https://example.com/fed-policy-shift",
                    "publishedAt": "2026-04-10T01:02:03Z",
                    "description": "Markets react to the new guidance.",
                    "source": {"name": "Reuters"},
                }
            ],
        }
    )
    items = health._parse_newsapi_items(payload, "https://newsapi.org/v2/top-headlines?country=us")
    assert len(items) == 1
    assert items[0]["headline"] == "Fed signals policy shift"
    assert items[0]["source_type"] == "newsapi"
    assert items[0]["source_url"] == "https://example.com/fed-policy-shift"


def test_canary_source_health_parses_rss_and_atom_payloads(tmp_path):
    health = CanarySourceHealth(audit_dir=str(tmp_path))
    rss_payload = """
    <rss version="2.0">
      <channel>
        <item>
          <title>Fed signals policy shift</title>
          <link>https://example.com/rss-item</link>
          <pubDate>Thu, 10 Apr 2026 01:02:03 GMT</pubDate>
          <description>RSS summary</description>
        </item>
      </channel>
    </rss>
    """
    atom_payload = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Markets open higher</title>
        <link href="https://example.com/atom-item" rel="alternate" />
        <updated>2026-04-10T01:02:03Z</updated>
        <summary>Atom summary</summary>
      </entry>
    </feed>
    """

    rss_items = health._parse_feed_items(rss_payload, "https://feeds.example.com/rss")
    atom_items = health._parse_feed_items(atom_payload, "https://feeds.example.com/atom")

    assert len(rss_items) == 1
    assert rss_items[0]["headline"] == "Fed signals policy shift"
    assert rss_items[0]["source_url"] == "https://example.com/rss-item"
    assert rss_items[0]["source_type"] == "rss"
    assert len(atom_items) == 1
    assert atom_items[0]["headline"] == "Markets open higher"
    assert atom_items[0]["source_url"] == "https://example.com/atom-item"
    assert atom_items[0]["source_type"] == "atom"


def test_canary_source_health_fetches_rss_source_once(tmp_path, monkeypatch):
    rss_payload = """
    <rss version="2.0">
      <channel>
        <item>
          <title>Fed signals policy shift</title>
          <link>https://example.com/rss-item</link>
          <pubDate>Thu, 10 Apr 2026 01:02:03 GMT</pubDate>
          <description>RSS summary</description>
        </item>
      </channel>
    </rss>
    """

    class FakeResponse:
        def __init__(self, payload: str):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self.payload.encode("utf-8")

    def fake_urlopen(req, timeout):
        return FakeResponse(rss_payload)

    monkeypatch.setattr(csh.urllib.request, "urlopen", fake_urlopen)
    health = CanarySourceHealth(audit_dir=str(tmp_path))
    out = health._fetch_source_once({"url": "https://example.com/rss", "kind": "rss"}, 5, 10)

    assert out["status"] == "success"
    assert out["items"][0]["headline"] == "Fed signals policy shift"
    assert out["items"][0]["source_type"] == "rss"


def test_canary_source_health_yellow_without_samples(tmp_path):
    health = CanarySourceHealth(audit_dir=str(tmp_path))
    summary = health.read_summary()
    assessment = health.assess(summary=summary, mode="dev")
    assert assessment.status == "YELLOW"
    assert "No live canary samples" in assessment.summary
