import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from data_adapter import DataAdapter


def test_data_adapter_fetch(monkeypatch):
    adapter = DataAdapter()
    monkeypatch.setattr(
        adapter,
        "fetch_news",
        lambda: {
            "headline": "test",
            "source": "s",
            "source_url": "s",
            "source_type": "rss",
            "timestamp": "2026-01-01T00:00:00Z",
            "raw_text": "x",
            "metadata": {},
        },
        raising=False,
    )
    monkeypatch.setattr(
        adapter,
        "fetch_market_data",
        lambda: {
            "vix_level": None,
            "vix_change_pct": None,
            "spx_change_pct": None,
            "etf_volatility": {"change_pct": None},
            "market_data_source": "failed",
            "is_test_data": True,
        },
        raising=False,
    )
    monkeypatch.setattr(adapter, "fetch_sector_data", lambda: [], raising=False)

    data = adapter.fetch()
    assert "news" in data
    assert "market_data" in data
    assert "headline" in data["news"]
    assert "vix_level" in data["market_data"]
    assert "sector_data" in data
    assert isinstance(data["sector_data"], list)
    assert data["market_data"].get("is_test_data") is True


def test_fetch_market_data_reports_realtime_source_when_fetchers_succeed(monkeypatch):
    adapter = DataAdapter()
    monkeypatch.setattr(adapter, "_fetch_vix", lambda: {"level": 18.2, "change_pct": 1.5}, raising=False)
    monkeypatch.setattr(adapter, "_fetch_spx", lambda: {"change_pct": -0.4}, raising=False)

    out = adapter.fetch_market_data()

    assert out["market_data_source"] == "realtime"
    assert out["is_test_data"] is False
    assert out["vix_level"] == 18.2
    assert out["vix_change_pct"] == 1.5
    assert out["spx_change_pct"] == -0.4


def test_fetch_market_data_returns_failed_shape_when_fetchers_unavailable(monkeypatch):
    adapter = DataAdapter()
    monkeypatch.setattr(adapter, "_fetch_vix", lambda: None, raising=False)
    monkeypatch.setattr(adapter, "_fetch_spx", lambda: None, raising=False)

    out = adapter.fetch_market_data()

    assert out["market_data_source"] == "failed"
    assert out["is_test_data"] is True
    assert out["vix_level"] is None
    assert out["vix_change_pct"] is None
    assert out["spx_change_pct"] is None


def test_fetch_market_data_returns_failed_shape_on_partial_success(monkeypatch):
    adapter = DataAdapter()
    monkeypatch.setattr(adapter, "_fetch_vix", lambda: {"level": 18.2, "change_pct": 1.5}, raising=False)
    monkeypatch.setattr(adapter, "_fetch_spx", lambda: None, raising=False)

    out = adapter.fetch_market_data()

    assert out["market_data_source"] == "failed"
    assert out["is_test_data"] is True
    assert out["vix_level"] is None
    assert out["spx_change_pct"] is None


def test_data_adapter_health_report_records_snapshots(tmp_path):
    adapter = DataAdapter(audit_dir=str(tmp_path))
    adapter.fetch()
    adapter.fetch()

    report = adapter.health_report()
    assert report["total_fetches"] >= 2
    assert "live_news_count" in report
    assert "fallback_news_count" in report
    assert (tmp_path / "data_health.jsonl").exists()
    assert (tmp_path / "data_health_summary.json").exists()
