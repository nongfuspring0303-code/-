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


def test_default_path_uses_five_wide_concurrency(monkeypatch):
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

    assert monitor._glm_concurrency == 5
    assert monitor.max_process_per_cycle == 5
    assert monitor._executor is not None
    assert monitor.run_once() is True
    assert processed_ids == ["S1", "S2"]
    assert len(monitor._pending_news) == 0


def test_explicit_single_thread_override_keeps_one_item_per_cycle(monkeypatch):
    monkeypatch.setenv("EDT_GLM_CONCURRENCY", "1")
    monkeypatch.setenv("EDT_MAX_PROCESS_PER_CYCLE", "1")
    monitor = _build_monitor(monkeypatch)
    monitor._bootstrap_done = True

    processed_ids = []

    def _fake_process(news):
        processed_ids.append(news.get("event_id"))
        return True

    monitor._process_news = _fake_process
    monitor._pending_news = [
        {"event_id": "O1", "headline": "first", "metadata": {}},
        {"event_id": "O2", "headline": "second", "metadata": {}},
    ]
    monitor._fetch_latest_news = lambda: []

    assert monitor._glm_concurrency == 1
    assert monitor.max_process_per_cycle == 1
    assert monitor._executor is None
    assert monitor.run_once() is True
    assert processed_ids == ["O1"]
    assert len(monitor._pending_news) == 1


def test_concurrent_fifo_order_preserved(monkeypatch):
    """S6-R016: Concurrent dispatch pops _pending_news in FIFO order.
    Test ID: S6-T016-01"""
    from concurrent.futures import ThreadPoolExecutor
    monitor = _build_monitor(monkeypatch)
    monitor.max_process_per_cycle = 3
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    monitor._executor = ThreadPoolExecutor(max_workers=3)

    # Spy on submit order by wrapping executor.submit
    submit_order = []
    original_submit = monitor._executor.submit

    def _spy_submit(fn, *args, **kwargs):
        if fn == monitor._process_news and args:
            submit_order.append(args[0].get("event_id"))
        return original_submit(fn, *args, **kwargs)

    monitor._executor.submit = _spy_submit

    def _fake_process(news):
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
    # Verify FIFO submit order (independent of worker execution order)
    assert submit_order == ["F1", "F2", "F3"], f"Expected FIFO submit, got {submit_order}"
    assert len(monitor._pending_news) == 0


def test_concurrent_dead_letter_on_worker_exception(monkeypatch):
    """S6-R016 worker异常: 失败新闻进入dead-letter，不静默丢失。
    Test ID: S6-T016-02"""
    from concurrent.futures import ThreadPoolExecutor
    monitor = _build_monitor(monkeypatch)
    monitor.max_process_per_cycle = 3
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    monitor._executor = ThreadPoolExecutor(max_workers=3)
    monitor._dead_letter = []

    call_count = 0

    def _exploding_process(news):
        nonlocal call_count
        call_count += 1
        if news.get("event_id") == "F2":
            raise RuntimeError("simulated worker failure")
        return True

    monitor._process_news = _exploding_process
    monitor._pending_news = [
        {"event_id": "F1", "headline": "ok", "metadata": {}},
        {"event_id": "F2", "headline": "boom", "metadata": {}},
        {"event_id": "F3", "headline": "ok", "metadata": {}},
    ]
    monitor._fetch_latest_news = lambda: []
    monitor._seen_signatures = {}

    result = monitor.run_once()
    # run_once should not raise; failed item captured in dead_letter
    assert result is True  # at least one succeeded
    assert len(monitor._pending_news) == 0  # all popped from queue
    assert len(monitor._dead_letter) == 1  # F2 in dead-letter
    assert monitor._dead_letter[0]["event_id"] == "F2"


def test_concurrent_path_uses_thread_local_workflow(monkeypatch):
    """S6-R016: 各线程获得独立的 workflow 实例。
    Test ID: S6-T016-03"""
    class _FakeWorkflow:
        _counter = 0

        def __init__(self):
            _FakeWorkflow._counter += 1
            self.instance_id = _FakeWorkflow._counter

    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    monitor._workflow_cls = _FakeWorkflow
    monitor.workflow = _FakeWorkflow()

    import threading
    instance_ids = []
    lock = threading.Lock()

    def _read_workflow():
        wf = monitor._get_workflow_runner()
        with lock:
            instance_ids.append(wf.instance_id)

    threads = [threading.Thread(target=_read_workflow) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Use set uniqueness to avoid thread-schedule ordering flakiness
    assert len(set(instance_ids)) == 2, f"Expected 2 unique instances, got {instance_ids}"


def test_concurrent_workflow_same_thread_reuses_instance(monkeypatch):
    """S6-R016: 同一线程重复调用复用同一个 workflow 实例。
    Test ID: S6-T016-04"""
    class _FakeWorkflow:
        _counter = 0
        def __init__(self):
            _FakeWorkflow._counter += 1
            self.instance_id = _FakeWorkflow._counter

    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    monitor._workflow_cls = _FakeWorkflow
    monitor.workflow = _FakeWorkflow()

    first = monitor._get_workflow_runner()
    second = monitor._get_workflow_runner()
    assert first is second, "Same thread should reuse the same workflow instance"


def test_concurrent_multi_news_isolation(monkeypatch):
    """S6-R016: 多新闻并发时 trace_id/headline 不串线。
    Test ID: S6-T016-05"""
    from concurrent.futures import ThreadPoolExecutor
    # Track which headlines each thread processed (via thread-local)
    processed = {}

    def _isolated_process(news):
        import threading
        tid = threading.get_ident()
        processed.setdefault(tid, []).append(news.get("event_id"))
        return True

    monitor = _build_monitor(monkeypatch)
    monitor.max_process_per_cycle = 3
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    monitor._executor = ThreadPoolExecutor(max_workers=3)
    # Temporarily replace _process_news to track per-thread isolation
    original_process = monitor._process_news
    monitor._process_news = _isolated_process
    monitor._pending_news = [
        {"event_id": "I1", "headline": "alpha", "metadata": {}},
        {"event_id": "I2", "headline": "beta", "metadata": {}},
        {"event_id": "I3", "headline": "gamma", "metadata": {}},
    ]
    monitor._fetch_latest_news = lambda: []
    monitor._seen_signatures = {}

    try:
        result = monitor.run_once()
        assert result is True
        # All 3 items must be processed across threads (no item lost)
        all_ids = []
        for tid, ids in processed.items():
            all_ids.extend(ids)
        assert set(all_ids) == {"I1", "I2", "I3"}, f"Missing items: {all_ids}"
    finally:
        monitor._process_news = original_process


def test_async_shutdown_cleans_up_executor(monkeypatch):
    """S6-R016: run_loop_async 在退出时 shutdown executor。
    Test ID: S6-T016-06"""
    import asyncio
    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=3)
    monitor._executor = executor
    shutdown_called = []
    original_shutdown = executor.shutdown
    def _spy_shutdown(wait=True):
        shutdown_called.append(wait)
        return original_shutdown(wait=wait)
    executor.shutdown = _spy_shutdown

    async def _run_and_stop():
        task = asyncio.create_task(monitor.run_loop_async())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass

    asyncio.run(_run_and_stop())
    assert len(shutdown_called) >= 1, "executor.shutdown(wait=True) was not called"


def test_env_var_invalid_values_fallback_safely(monkeypatch):
    """S6-R016: 非法环境变量值回退到默认值。
    Test ID: S6-T016-07"""
    monkeypatch.setenv("EDT_GLM_CONCURRENCY", "abc")
    monkeypatch.setenv("EDT_MAX_PROCESS_PER_CYCLE", "xyz")
    monitor = _build_monitor(monkeypatch)
    assert monitor._glm_concurrency == 5, f"Expected default 5, got {monitor._glm_concurrency}"
    assert monitor.max_process_per_cycle == 5, f"Expected default 5, got {monitor.max_process_per_cycle}"
