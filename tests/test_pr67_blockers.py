"""
Minimal regression tests for PR #67 review blockers.

1. Config missing -> semantic must abstain (no silent local gateway fallback).
2. Batch path -> test/fallback data must be blocked in _process_news.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pytest
from ai_semantic_analyzer import SemanticAnalyzer


# --- Blocker-1: OPENAI_BASE_URL missing must raise, not silently fallback ---

def test_openai_base_url_missing_raises(tmp_path, monkeypatch):
    """When OPENAI_BASE_URL is not configured, _openai_base_url() must raise."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("modules: {}\nruntime:\n  semantic:\n    enabled: true\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_CONFIG", raising=False)

    analyzer = SemanticAnalyzer(config_path=str(cfg))
    with pytest.raises(RuntimeError, match="OPENAI_BASE_URL is not configured"):
        analyzer._openai_base_url()


def test_analyze_abstains_when_base_url_missing(tmp_path, monkeypatch):
    """When OPENAI_BASE_URL is missing, analyze() should return abstain, not crash."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    provider: openai\n    model: gpt-4\n    min_confidence: 10\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_CONFIG", raising=False)

    analyzer = SemanticAnalyzer(config_path=str(cfg))
    out = analyzer.analyze("test headline", "raw text")
    # Must abstain with a clear reason
    assert out["verdict"] == "abstain"
    assert out.get("fallback_reason") == "openai_base_url_missing"
    assert "OPENAI_BASE_URL" in out.get("fallback_detail", "")


# --- Blocker-2: batch path must block test/fallback data ---

def test_normalize_preserves_is_test_data(monkeypatch):
    """_normalize_news_item must pass through is_test_data and is_fallback markers."""
    from data_adapter import DataAdapter

    adapter = DataAdapter()

    # Test is_test_data passthrough
    item = adapter._normalize_news_item({
        "headline": "Test news",
        "source_url": "https://example.com",
        "source_type": "test",
        "source_mode": "pull",
        "timestamp": "2026-01-01T00:00:00Z",
        "raw_text": "",
        "event_id": "TEST-001",
        "is_test_data": True,
        "metadata": {"provenance": "test_fixture", "keywords": ["alpha"]},
    })
    assert item["metadata"]["is_test_data"] is True
    assert item["metadata"]["provenance"] == "test_fixture"
    assert item["is_test_data"] is True

    # Test is_fallback passthrough
    item2 = adapter._normalize_news_item({
        "headline": "Fallback news",
        "source_url": "https://example.com",
        "source_type": "fallback",
        "source_mode": "pull",
        "timestamp": "2026-01-01T00:00:00Z",
        "raw_text": "",
        "event_id": "FALLBACK-001",
        "is_fallback": True,
    })
    assert item2["metadata"]["is_test_data"] is True

    # Test clean data has is_test_data=False
    item3 = adapter._normalize_news_item({
        "headline": "Real news",
        "source_url": "https://reuters.com",
        "source_type": "sina",
        "source_mode": "push",
        "timestamp": "2026-01-01T00:00:00Z",
        "raw_text": "",
        "event_id": "SINA-123",
    })
    assert item3["metadata"]["is_test_data"] is False


def test_batch_path_news_is_blocked_by_monitor(monkeypatch):
    """Batch-normalized test-data news must be blocked by monitor gate."""
    from data_adapter import DataAdapter
    from realtime_news_monitor import RealtimeNewsMonitor

    class _FakeCapture:
        def run(self, _news):
            class _Out:
                data = {"captured": True, "matched_keywords": ["x"], "vix_amplify": False}

            return _Out()

    def _fake_load(self):
        self.event_capture = _FakeCapture()
        self.data_adapter = None
        self.workflow = None

    monkeypatch.setattr(RealtimeNewsMonitor, "_load_news_module", _fake_load)
    monitor = RealtimeNewsMonitor()
    monitor._trigger_ab_pipeline = lambda _news: None

    adapter = DataAdapter()
    batch_item = adapter._normalize_news_item(
        {
            "headline": "Fallback sample",
            "source_url": "https://example.com/fallback",
            "source_type": "fallback",
            "source_mode": "pull",
            "timestamp": "2026-01-01T00:00:00Z",
            "raw_text": "sample",
            "event_id": "FB-1",
            "is_fallback": True,
            "metadata": {"provenance": "fallback_fixture"},
        }
    )
    assert batch_item["metadata"]["is_test_data"] is True
    assert monitor._process_news(batch_item) is False
