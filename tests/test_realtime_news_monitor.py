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
        self._event_capture_cls = None
        self._data_adapter_cls = None
        self._workflow_cls = None
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


def test_process_news_real_news_keyword_miss_does_not_trigger_ab(monkeypatch):
    class _MissCapture:
        def run(self, _news):
            class _Out:
                data = {"captured": False, "matched_keywords": [], "vix_amplify": False}

            return _Out()

    monitor = _build_monitor(monkeypatch)
    monitor.event_capture = _MissCapture()

    trigger_calls = {"count": 0}

    def _fake_trigger(_news):
        trigger_calls["count"] += 1

    monitor._trigger_ab_pipeline = _fake_trigger

    news = {
        "headline": "Routine company update",
        "source_type": "rss",
        "metadata": {},
    }

    result = monitor._process_news(news)

    assert result is False
    assert trigger_calls["count"] == 0


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


def test_translate_headline_falls_back_without_translator(monkeypatch):
    monitor = _build_monitor(monkeypatch)
    monitor.translator = None

    translated = monitor._translate_headline("Fed rate cut amid inflation and market stress")

    assert translated is not None
    assert "美联储" in translated
    assert "降息" in translated
    assert "通胀" in translated


def test_translate_headline_falls_back_when_translator_errors(monkeypatch):
    class _BoomTranslator:
        def translate(self, *_args, **_kwargs):
            raise RuntimeError("translator unavailable")

    monitor = _build_monitor(monkeypatch)
    monitor.translator = _BoomTranslator()

    translated = monitor._translate_headline("SEC warns about market risks")

    assert translated is not None
    assert "美国SEC" in translated
    assert "市场" in translated


def test_trace_id_consistent_across_preview_and_ab_updates(monkeypatch):
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

    # Simulate real news lacking event_id but carrying source_url.
    news = {
        "headline": "Fed officials still foresee rate cut",
        "source_url": "https://www.cnbc.com/example",
        "source_type": "rss",
        "source_mode": "push",
        "timestamp": "2026-04-08T18:00:00Z",
        "metadata": {},
    }
    monitor._push_news_preview(news)

    result = {
        "analysis": {
            "conduction": {
                "sector_impacts": [{"sector": "Energy", "direction": "benefit", "confidence": 80}],
                "confidence": 80,
            },
            "opportunity_update": {
                "opportunities": [
                    {"symbol": "XOM", "name": "Exxon", "sector": "Energy", "signal": "LONG"}
                ]
            },
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
    monitor._push_sectors_to_c(result, news=news, publish_event_update=True)

    related = [
        payload
        for url, payload in captured_posts
        if url.endswith("/api/ingest/event-update")
        or url.endswith("/api/ingest/sector-update")
        or url.endswith("/api/ingest/opportunity-update")
    ]
    assert related, "expected ingest payloads to be posted"

    trace_ids = {str(payload.get("trace_id", "")) for payload in related}
    assert len(trace_ids) == 1
    assert trace_ids == {monitor._build_live_trace_id(news)}

    opp_posts = [payload for url, payload in captured_posts if url.endswith("/api/ingest/opportunity-update")]
    assert len(opp_posts) == 1


def test_run_once_queues_fresh_news_without_dropping(monkeypatch):
    monitor = _build_monitor(monkeypatch)
    monitor._bootstrap_done = True
    monitor.max_process_per_cycle = 1

    processed_ids = []

    def _fake_process(news):
        processed_ids.append(news.get("event_id"))
        return True

    # Ingestion order is typically newest -> oldest.
    news_batch = [
        {"event_id": "N2", "headline": "newer", "timestamp": "2026-04-20T10:00:10Z", "metadata": {}},
        {"event_id": "N1", "headline": "older", "timestamp": "2026-04-20T10:00:00Z", "metadata": {}},
    ]
    monitor._fetch_latest_news = lambda: news_batch
    monitor._process_news = _fake_process

    # First round: enqueue both, process 1 due to max_process_per_cycle=1.
    assert monitor.run_once() is True
    assert processed_ids == ["N1"]
    assert len(monitor._pending_news) == 1

    # Second round: no fresh items, but pending queue still drains.
    monitor._fetch_latest_news = lambda: []
    assert monitor.run_once() is True
    assert processed_ids == ["N1", "N2"]
    assert len(monitor._pending_news) == 0


def test_default_path_keeps_single_item_in_thread(monkeypatch):
    monitor = _build_monitor(monkeypatch)
    monitor._bootstrap_done = True

    processed_ids = []

    def _fake_process(news):
        processed_ids.append(news.get("event_id"))
        return True

    monitor._process_news = _fake_process
    monitor._pending_news = [
        {"event_id": "S1", "headline": "first", "metadata": {}},
        {"event_id": "S2", "headline": "second", "metadata": {}},
    ]
    monitor._fetch_latest_news = lambda: []

    assert monitor._glm_concurrency == 1
    assert monitor.max_process_per_cycle == 1
    assert monitor._executor is None
    assert monitor.run_once() is True
    assert processed_ids == ["S1"]
    assert len(monitor._pending_news) == 1


def test_concurrent_fifo_order_preserved(monkeypatch):
    """S6-R016: Concurrent dispatch dequeues _pending_news in FIFO order.
    Test ID: S6-T016-01"""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    monitor = _build_monitor(monkeypatch)
    monitor.max_process_per_cycle = 3
    monitor._glm_concurrency = 3
    monitor._executor = ThreadPoolExecutor(max_workers=3)

    dequeue_order = []
    lock = threading.Lock()

    def _fake_process(news):
        with lock:
            dequeue_order.append(news.get("event_id"))
        return True

    monitor._process_news = _fake_process
    monitor._pending_news = [
        {"event_id": "F1", "headline": "first", "metadata": {}},
        {"event_id": "F2", "headline": "second", "metadata": {}},
        {"event_id": "F3", "headline": "third", "metadata": {}},
    ]
    monitor._fetch_latest_news = lambda: []
    monitor._seen_signatures = {}

    result = monitor.run_once()
    assert result is True
    # Items must be dequeued in FIFO order from _pending_news
    assert dequeue_order == ["F1", "F2", "F3"], f"Expected FIFO dequeue, got {dequeue_order}"
    assert len(monitor._pending_news) == 0


def test_concurrent_path_uses_thread_local_workflow(monkeypatch):
    class _FakeWorkflow:
        created = 0

        def __init__(self):
            type(self).created += 1
            self.instance_id = type(self).created

    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    monitor._workflow_cls = _FakeWorkflow
    monitor.workflow = _FakeWorkflow()

    import threading

    instance_ids = []
    lock = threading.Lock()

    def _read_workflow():
        workflow = monitor._get_workflow_runner()
        with lock:
            instance_ids.append(workflow.instance_id)

    threads = [threading.Thread(target=_read_workflow) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert instance_ids == [2, 3]
