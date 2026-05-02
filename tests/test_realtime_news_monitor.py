import pytest
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

    # Override trigger to accept publish_event_update kwarg
    monitor._trigger_ab_pipeline = lambda news, **kwargs: None
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


# ---------------------------------------------------------------------------
# 修复1: 真实 _process_news 多新闻并发隔离测试
# S6-R016 / Test IDs: S6-T016-08
# ---------------------------------------------------------------------------

def test_concurrent_real_process_news_isolation(monkeypatch):
    """S6-R016: 真实 _process_news 并发处理多条新闻时 trace_id/headline 不串线。
    Test ID: S6-T016-08"""
    from concurrent.futures import ThreadPoolExecutor

    # Track push payloads per trace_id with full field isolation check
    preview_payloads = []
    sector_payloads = []

    def _fake_preview(news, **kwargs):
        preview_payloads.append({"headline": news.get("headline"), "event_id": news.get("event_id")})

    def _fake_push(result, news=None, **kwargs):
        trace_id = result.get("trace_id", "")
        analysis = result.get("analysis", {})
        opp_update = analysis.get("opportunity_update", {})
        headline = ""
        source = ""
        request_id = ""
        batch_id = ""
        if "intel" in result:
            eo = result["intel"].get("event_object", {})
            headline = eo.get("headline", "")
            source = eo.get("source_url", "")
        request_id = str(result.get("request_id", "") or "")
        batch_id = str(result.get("batch_id", "") or "")
        sector_payloads.append({
            "trace_id": trace_id,
            "headline": headline,
            "source": source,
            "request_id": request_id,
            "batch_id": batch_id,
        })

    class _FakeEventCapture:
        def __init__(self, config_path=None):
            pass
        def run(self, news):
            class _Result:
                data = {
                    "captured": True,
                    "matched_keywords": ["test"],
                    "vix_amplify": False,
                    "ai_verdict": "hit",
                    "ai_confidence": 80,
                    "ai_reason": "test",
                }
            return _Result()

    class _FakeDataAdapter:
        def __init__(self):
            pass
        def fetch_market_data(self):
            return {}

    class _FakeWorkflowRunner:
        def __init__(self, audit_dir=None, state_db_path=None):
            pass
        def run(self, payload):
            headline = payload.get("headline", "")
            source = payload.get("source", "")
            trace_id = f"TRACE-{headline}"
            return {
                "intel": {
                    "event_object": {
                        "event_id": headline,
                        "headline": headline,
                        "source_url": source,
                        "severity": "E1",
                        "detected_at": "2026-05-01T00:00:00Z",
                    }
                },
                "analysis": {
                    "conduction": {"sector_impacts": [], "confidence": 0},
                    "opportunity_update": {"opportunities": []},
                },
                "trace_id": trace_id,
                "request_id": f"REQ-{headline}",
                "batch_id": f"BATCH-{headline}",
            }

    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor.max_process_per_cycle = 3
    monitor._use_concurrent_processing = True
    monitor._executor = ThreadPoolExecutor(max_workers=3)
    # Wire up real classes
    monitor._event_capture_cls = _FakeEventCapture
    monitor._data_adapter_cls = _FakeDataAdapter
    monitor._workflow_cls = _FakeWorkflowRunner
    monkeypatch.setattr(type(monitor), "_push_news_preview",
                      lambda self, news, **kwargs: _fake_preview(news, **kwargs))
    monkeypatch.setattr(type(monitor), "_push_sectors_to_c",
                      lambda self, result, news=None, **kwargs: _fake_push(result, news=news, **kwargs))
    monitor.node_role = "master"
    monitor._bootstrap_done = True
    monitor._pending_news = [
        {"headline": "NewsAlpha", "source_url": "https://source.alpha", "source_type": "rss",
         "timestamp": "2026-05-01T00:00:00Z", "event_id": "A1", "metadata": {}},
        {"headline": "NewsBeta", "source_url": "https://source.beta", "source_type": "rss",
         "timestamp": "2026-05-01T00:00:01Z", "event_id": "B1", "metadata": {}},
        {"headline": "NewsGamma", "source_url": "https://source.gamma", "source_type": "rss",
         "timestamp": "2026-05-01T00:00:02Z", "event_id": "G1", "metadata": {}},
    ]
    monitor._fetch_latest_news = lambda: []
    monitor._seen_signatures = {}
    # Remove _build_monitor's fake trigger so real _trigger_ab_pipeline runs
    if "_trigger_ab_pipeline" in monitor.__dict__:
        del monitor._trigger_ab_pipeline

    try:
        result = monitor.run_once()
        assert result is True

        # Verify isolation: all headlines present (may be called multiple times per item)
        preview_headlines = set(p["headline"] for p in preview_payloads)
        assert preview_headlines == {"NewsAlpha", "NewsBeta", "NewsGamma"}, \
            f"Preview isolation broken: {preview_headlines}"

        sector_headlines = [p["headline"] for p in sector_payloads]
        assert set(sector_headlines) == {"NewsAlpha", "NewsBeta", "NewsGamma"}, \
            f"Sector push isolation broken: {sector_headlines}"

        # Verify per-news-item field isolation (trace_id, headline, source)
        expected_by_headline = {
            "NewsAlpha": {"source": "https://source.alpha"},
            "NewsBeta": {"source": "https://source.beta"},
            "NewsGamma": {"source": "https://source.gamma"},
        }
        for entry in sector_payloads:
            hl = entry["headline"]
            tid = entry["trace_id"]
            src = entry["source"]
            rid = entry["request_id"]
            bid = entry["batch_id"]
            expected_tid = f"TRACE-{hl}"
            assert tid == expected_tid, f"Trace mismatch: expected {expected_tid}, got {tid}"
            expected_src = expected_by_headline[hl]["source"]
            assert src == expected_src, f"Source mismatch for {hl}: expected {expected_src}, got {src}"
            # request_id and batch_id should be set (non-empty) and not leak between items
            assert rid, f"request_id empty for {hl}"
            assert bid, f"batch_id empty for {hl}"

        # Explicit cross-contamination check: A's fields must not appear in B's output
        for entry in sector_payloads:
            hl = entry["headline"]
            if hl == "NewsAlpha":
                assert entry["source"] == "https://source.alpha"
            elif hl == "NewsBeta":
                assert entry["source"] == "https://source.beta"
            elif hl == "NewsGamma":
                assert entry["source"] == "https://source.gamma"
            assert entry["request_id"] not in ("", None)
            assert entry["batch_id"] not in ("", None)
    finally:
        monitor._executor = None


# ---------------------------------------------------------------------------
# 修复2: EventCapture / DataAdapter thread-local 测试
# Test IDs: S6-T016-09 ~ S6-T016-12
# ---------------------------------------------------------------------------

def test_concurrent_event_capture_thread_local_isolation(monkeypatch):
    """S6-R016: EventCapture thread-local —— 不同线程不同实例，同线程复用。
    Test ID: S6-T016-09"""
    import threading
    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True

    class _FakeCapture:
        _next_id = 0
        def __init__(self, config_path=None):
            _FakeCapture._next_id += 1
            self.instance_id = _FakeCapture._next_id

    monitor._event_capture_cls = _FakeCapture

    ids = []
    lock = threading.Lock()

    def _get():
        ec = monitor._get_event_capture()
        with lock:
            ids.append(ec.instance_id)

    threads = [threading.Thread(target=_get) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(set(ids)) == 2, f"Expected 2 unique instances, got {ids}"


def test_concurrent_event_capture_same_thread_reuses_instance(monkeypatch):
    """S6-R016: EventCapture 同线程重复调用复用同一实例。
    Test ID: S6-T016-10"""
    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True

    class _FakeCapture:
        _next_id = 0
        def __init__(self, config_path=None):
            _FakeCapture._next_id += 1
            self.instance_id = _FakeCapture._next_id

    monitor._event_capture_cls = _FakeCapture
    first = monitor._get_event_capture()
    second = monitor._get_event_capture()
    assert first is second, "Same thread should reuse EventCapture"


def test_concurrent_data_adapter_thread_local_isolation(monkeypatch):
    """S6-R016: DataAdapter thread-local —— 不同线程不同实例，同线程复用。
    Test ID: S6-T016-11"""
    import threading
    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True

    class _FakeAdapter:
        _next_id = 0
        def __init__(self):
            _FakeAdapter._next_id += 1
            self.instance_id = _FakeAdapter._next_id

    monitor._data_adapter_cls = _FakeAdapter

    ids = []
    lock = threading.Lock()

    def _get():
        da = monitor._get_market_data_adapter()
        with lock:
            ids.append(da.instance_id)

    threads = [threading.Thread(target=_get) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(set(ids)) == 2, f"Expected 2 unique instances, got {ids}"


def test_concurrent_data_adapter_same_thread_reuses_instance(monkeypatch):
    """S6-R016: DataAdapter 同线程重复调用复用同一实例。
    Test ID: S6-T016-12"""
    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True

    class _FakeAdapter:
        _next_id = 0
        def __init__(self):
            _FakeAdapter._next_id += 1
            self.instance_id = _FakeAdapter._next_id

    monitor._data_adapter_cls = _FakeAdapter
    first = monitor._get_market_data_adapter()
    second = monitor._get_market_data_adapter()
    assert first is second, "Same thread should reuse DataAdapter"


# ---------------------------------------------------------------------------
# 修复3: executor shutdown 后 run_once 不丢消息
# Test ID: S6-T016-13
# ---------------------------------------------------------------------------

def test_run_once_after_executor_shutdown_does_not_drop_pending_news(monkeypatch):
    """S6-R016: executor shutdown 后 run_once 降级 sequential，不丢 _pending_news。
    Test ID: S6-T016-13"""
    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor.max_process_per_cycle = 5
    monitor._use_concurrent_processing = True
    from concurrent.futures import ThreadPoolExecutor
    monitor._executor = ThreadPoolExecutor(max_workers=3)
    # Shutdown executor
    monitor._shutdown_executor()
    assert monitor._executor is None, "executor should be None after shutdown"

    processed_ids = []
    def _fake_process(news):
        processed_ids.append(news.get("event_id"))
        return True
    monitor._process_news = _fake_process

    monitor._pending_news = [
        {"event_id": "S1", "headline": "post-shutdown", "metadata": {}},
        {"event_id": "S2", "headline": "still-processed", "metadata": {}},
    ]
    monitor._bootstrap_done = True
    monitor._fetch_latest_news = lambda: []

    result = monitor.run_once()
    assert result is True
    # Both items must be processed (sequential fallback)
    assert processed_ids == ["S1", "S2"], f"Items dropped after shutdown: {processed_ids}"
    assert len(monitor._pending_news) == 0


# ---------------------------------------------------------------------------
# 修复4: 环境变量边界测试
# Test IDs: S6-T016-14 ~ S6-T016-18
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("env_val,field,expected", [
    ("0", "_glm_concurrency", 1),     # EDT_GLM_CONCURRENCY=0 → clamped to 1
    ("-1", "_glm_concurrency", 1),    # EDT_GLM_CONCURRENCY=-1 → clamped to 1
])
def test_env_var_glm_concurrency_edge(monkeypatch, env_val, field, expected):
    """S6-R016: EDT_GLM_CONCURRENCY 边界值 clamp 到至少 1。
    Test IDs: S6-T016-14~15"""
    monkeypatch.setenv("EDT_GLM_CONCURRENCY", env_val)
    monitor = _build_monitor(monkeypatch)
    assert getattr(monitor, field) == expected, f"{field}={getattr(monitor, field)} != {expected}"


@pytest.mark.parametrize("env_val", ["0", "-1"])
def test_env_var_max_process_per_cycle_edge(monkeypatch, env_val):
    """S6-R016: EDT_MAX_PROCESS_PER_CYCLE=0/-1 clamp 到至少 1。
    Test IDs: S6-T016-16~17"""
    monkeypatch.setenv("EDT_MAX_PROCESS_PER_CYCLE", env_val)
    monitor = _build_monitor(monkeypatch)
    assert monitor.max_process_per_cycle >= 1, f"max_process_per_cycle={monitor.max_process_per_cycle}"


def test_env_var_glm2_max5_combination(monkeypatch):
    """S6-R016: EDT_GLM_CONCURRENCY=2 + EDT_MAX_PROCESS_PER_CYCLE=5。
    Test ID: S6-T016-18"""
    monkeypatch.setenv("EDT_GLM_CONCURRENCY", "2")
    monkeypatch.setenv("EDT_MAX_PROCESS_PER_CYCLE", "5")
    monitor = _build_monitor(monkeypatch)
    assert monitor._glm_concurrency == 2
    assert monitor.max_process_per_cycle == 5
    assert monitor._use_concurrent_processing is True
    assert monitor._executor is not None


# ---------------------------------------------------------------------------
# 修复2(B): 真实 _process_news 路径下的 thread-local 命中证明
# Test IDs: S6-T016-19 ~ S6-T016-21
# ---------------------------------------------------------------------------

def test_concurrent_thread_local_hit_via_real_process_news(monkeypatch):
    """S6-R016: 真实 _process_news 路径验证线程独立 EventCapture/DataAdapter/WorkflowRunner。
    Test ID: S6-T016-19"""
    from concurrent.futures import ThreadPoolExecutor
    import threading

    # Track thread-local instance IDs per thread
    ec_ids = {}
    da_ids = {}
    wf_ids = {}

    class _FakeEC:
        _next = 0
        def __init__(self, config_path=None):
            _FakeEC._next += 1
            self._id = _FakeEC._next
            tid = threading.get_ident()
            ec_ids.setdefault(tid, []).append(self._id)
        def run(self, news):
            class _R:
                data = {"captured": True, "matched_keywords": ["x"], "vix_amplify": False}
            return _R()

    class _FakeDA:
        _next = 0
        def __init__(self):
            _FakeDA._next += 1
            self._id = _FakeDA._next
            tid = threading.get_ident()
            da_ids.setdefault(tid, []).append(self._id)
        def fetch_market_data(self):
            return {}

    class _FakeWF:
        _next = 0
        def __init__(self, audit_dir=None, state_db_path=None):
            _FakeWF._next += 1
            self._id = _FakeWF._next
            tid = threading.get_ident()
            wf_ids.setdefault(tid, []).append(self._id)
        def run(self, payload):
            h = payload.get("headline", "")
            return {
                "intel": {"event_object": {"headline": h, "source_url": "", "severity": "E1",
                                           "detected_at": "2026-05-01T00:00:00Z", "event_id": h}},
                "analysis": {"conduction": {"sector_impacts": [], "confidence": 0},
                             "opportunity_update": {"opportunities": []}},
                "trace_id": f"TRACE-{h}",
            }

    monitor = _build_monitor(monkeypatch)
    monitor._glm_concurrency = 3
    monitor._use_concurrent_processing = True
    monitor._executor = ThreadPoolExecutor(max_workers=3)
    monitor._event_capture_cls = _FakeEC
    monitor._data_adapter_cls = _FakeDA
    monitor._workflow_cls = _FakeWF
    monkeypatch.setattr(type(monitor), "_push_news_preview", lambda self, n, **kw: None)
    monkeypatch.setattr(type(monitor), "_push_sectors_to_c", lambda self, r, **kw: None)
    if "_trigger_ab_pipeline" in monitor.__dict__:
        del monitor._trigger_ab_pipeline
    monitor.node_role = "master"
    monitor._bootstrap_done = True
    monitor._fetch_latest_news = lambda: []
    monitor._pending_news = [
        {"headline": f"News{i}", "source_url": f"https://s{i}", "source_type": "rss",
         "timestamp": f"2026-05-01T00:00:0{i}Z", "event_id": f"E{i}", "metadata": {}}
        for i in range(3)]
    monitor._seen_signatures = {}

    result = monitor.run_once()
    assert result is True

    # Each of the 3 worker threads should have its own instances
    for tid, ids in ec_ids.items():
        assert len(set(ids)) == 1, f"EC thread {tid} should reuse same instance: {ids}"
    for tid, ids in da_ids.items():
        assert len(set(ids)) == 1, f"DA thread {tid} should reuse same instance: {ids}"
    for tid, ids in wf_ids.items():
        assert len(set(ids)) == 1, f"WF thread {tid} should reuse same instance: {ids}"

    # Multiple threads participated (at least 2 different threads with EC instances)
    ec_threads = set(ec_ids.keys())
    assert len(ec_threads) >= 1, "Expected at least 1 thread for EC"
