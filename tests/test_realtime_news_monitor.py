import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_news_monitor import RealtimeNewsMonitor


class _FakeCapture:
    def run(self, _news):
        class _Out:
            data = {"captured": True, "matched_keywords": ["x"], "vix_amplify": False}

        return _Out()


def _build_monitor(monkeypatch):
    def _fake_load(self):
        self.event_capture = _FakeCapture()
        self.data_adapter = None
        self.workflow = None

    monkeypatch.setattr(RealtimeNewsMonitor, "_load_news_module", _fake_load)
    monitor = RealtimeNewsMonitor()
    monitor._trigger_ab_pipeline = lambda _news: None
    return monitor


def test_process_news_skips_fallback_source(monkeypatch):
    monitor = _build_monitor(monkeypatch)
    news = {
        "headline": "fallback headline",
        "source_type": "fallback",
        "metadata": {},
    }
    assert monitor._process_news(news) is False


def test_process_news_skips_failed_source(monkeypatch):
    monitor = _build_monitor(monkeypatch)
    news = {
        "headline": "failed headline",
        "source_type": "failed",
        "metadata": {},
    }
    assert monitor._process_news(news) is False


def test_process_news_skips_test_data_and_logs_warning(monkeypatch, caplog):
    monitor = _build_monitor(monkeypatch)
    news = {
        "headline": "test-data headline",
        "source_type": "rss",
        "metadata": {"is_test_data": True},
    }

    with caplog.at_level("WARNING"):
        result = monitor._process_news(news)

    assert result is False
    assert any("跳过非实盘新闻" in message for message in caplog.messages)


def test_push_event_update_uses_detected_at_as_news_timestamp(monkeypatch):
    captured_posts = []

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=10):
        import json

        payload = json.loads(req.data.decode("utf-8"))
        captured_posts.append((req.full_url, payload))
        return _FakeResponse()

    monitor = _build_monitor(monkeypatch)
    monitor.api_url = "http://127.0.0.1:9999"

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    monitor._push_sectors_to_c(
        {
            "analysis": {
                "conduction": {
                    "sector_impacts": [{"sector": "Energy", "direction": "benefit", "confidence": 80}],
                    "confidence": 80,
                },
                "opportunity_update": {"opportunities": []},
            },
            "intel": {
                "event_object": {
                    "event_id": "ME-D-20260409-001.V1.0",
                    "headline": "Fed officials still foresee rate cut",
                    "source_url": "https://www.cnbc.com/example",
                    "severity": "E0",
                    "detected_at": "2026-04-08T18:00:00Z",
                }
            },
            "trace_id": "ME-D-20260409-001.V1.0",
        }
    )

    event_posts = [payload for url, payload in captured_posts if url.endswith("/api/ingest/event-update")]
    assert len(event_posts) == 1
    assert event_posts[0]["news_timestamp"] == "2026-04-08T18:00:00Z"


def test_worker_node_skips_main_chain_push(monkeypatch):
    monitor = RealtimeNewsMonitor()
    monitor.node_role = "worker"

    called = {"value": False}

    def boom(*args, **kwargs):  # pragma: no cover - should not be reached
        called["value"] = True
        raise AssertionError("urlopen should not be called for worker nodes")

    monkeypatch.setattr("urllib.request.urlopen", boom)

    monitor._push_sectors_to_c({"analysis": {}, "intel": {}})

    assert called["value"] is False
