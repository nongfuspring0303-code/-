import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import market_data_adapter as mdamod
from market_data_adapter import MarketDataAdapter


def test_market_data_adapter_batch_cache_and_failover():
    # Rule ID: R-S4-001/R-S4-002/R-S4-003
    calls = {"primary": 0, "fallback": 0}

    def primary_provider(symbols):
        calls["primary"] += 1
        # primary only serves AAPL; TSLA must failover
        return {"AAPL": 190.0} if "AAPL" in symbols else {}

    def fallback_provider(symbols):
        calls["fallback"] += 1
        out = {}
        if "TSLA" in symbols:
            out["TSLA"] = 240.5
        return out

    now = {"ts": 1_000.0}

    def now_fn():
        return now["ts"]

    cfg = {
        "runtime.price_fetch.cache_ttl_seconds": 120,
        "runtime.price_fetch.max_batch_size": 2,
        "runtime.price_fetch.providers.active": ["primary"],
        "runtime.price_fetch.providers.fallback": ["fallback"],
        "runtime.price_fetch.providers.deprecated": [],
    }

    adapter = MarketDataAdapter(
        config_getter=lambda k, d=None: cfg.get(k, d),
        providers={"primary": primary_provider, "fallback": fallback_provider},
        now_fn=now_fn,
    )

    # first call: primary + fallback
    out1 = adapter.quote_many(["AAPL", "TSLA"])
    assert out1["AAPL"] == 190.0
    assert out1["TSLA"] == 240.5
    assert calls["primary"] == 1
    assert calls["fallback"] == 1
    assert adapter.last_meta.succeeded == ["primary", "fallback"]

    # second call within ttl: served from cache
    now["ts"] += 30
    out2 = adapter.quote_many(["AAPL", "TSLA"])
    assert out2 == out1
    assert calls["primary"] == 1
    assert calls["fallback"] == 1
    assert adapter.last_meta.from_cache == 2

    # expire cache -> providers called again
    now["ts"] += 200
    out3 = adapter.quote_many(["AAPL", "TSLA"])
    assert out3 == out1
    assert calls["primary"] == 2
    assert calls["fallback"] == 2


def test_market_data_adapter_respects_empty_provider_chain_without_network_side_effects():
    # Test ID: T-S4-EMPTY-CHAIN -> Rule ID: R-S4-CONFIG-ALIGN
    calls = {"primary": 0, "fallback": 0}

    def primary_provider(symbols):
        calls["primary"] += 1
        return {"AAPL": 1.0}

    def fallback_provider(symbols):
        calls["fallback"] += 1
        return {"AAPL": 1.0}

    cfg = {
        "runtime.price_fetch.providers.active": [],
        "runtime.price_fetch.providers.fallback": [],
        "runtime.price_fetch.providers.deprecated": [],
    }
    adapter = MarketDataAdapter(
        config_getter=lambda k, d=None: cfg.get(k, d),
        providers={"primary": primary_provider, "fallback": fallback_provider},
    )

    out = adapter.quote_many(["AAPL"])
    assert out == {}
    assert adapter.last_meta.provider_chain == []
    assert adapter.last_meta.attempted == []
    assert adapter.last_meta.succeeded == []
    assert adapter.last_meta.unresolved_symbols == ["AAPL"]
    assert calls["primary"] == 0
    assert calls["fallback"] == 0


def test_market_data_adapter_does_not_implicitly_fallback_when_deprecated_clears_chain():
    # Test ID: T-S4-DEPRECATED-CLEAR -> Rule ID: R-S4-CONFIG-ALIGN
    calls = {"yahoo": 0, "stooq": 0}

    def yahoo_provider(symbols):
        calls["yahoo"] += 1
        return {"AAPL": 1.0}

    def stooq_provider(symbols):
        calls["stooq"] += 1
        return {"AAPL": 1.0}

    cfg = {
        "runtime.price_fetch.providers.active": ["yahoo"],
        "runtime.price_fetch.providers.fallback": ["stooq"],
        "runtime.price_fetch.providers.deprecated": ["yahoo", "stooq"],
    }
    adapter = MarketDataAdapter(
        config_getter=lambda k, d=None: cfg.get(k, d),
        providers={"yahoo": yahoo_provider, "stooq": stooq_provider},
    )

    out = adapter.quote_many(["AAPL"])
    assert out == {}
    assert adapter.last_meta.provider_chain == []
    assert adapter.last_meta.attempted == []
    assert adapter.last_meta.unresolved_symbols == ["AAPL"]
    assert calls["yahoo"] == 0
    assert calls["stooq"] == 0


def test_market_data_adapter_yahoo_prefers_yfinance_before_http(monkeypatch):
    class _FakeTicker:
        def __init__(self, _symbol):
            self.fast_info = {"lastPrice": 209.09}

    class _FakeYF:
        @staticmethod
        def Ticker(symbol):
            return _FakeTicker(symbol)

    monkeypatch.setattr(mdamod, "yf", _FakeYF())

    def _unexpected_urlopen(*_args, **_kwargs):
        raise AssertionError("HTTP fallback should not be called when yfinance returns prices")

    monkeypatch.setattr(mdamod.urllib.request, "urlopen", _unexpected_urlopen)
    adapter = MarketDataAdapter()
    out = adapter._fetch_yahoo(["NVDA"])
    assert out == {"NVDA": 209.09}


def test_market_data_adapter_records_failed_providers_and_fallback_reason():
    cfg = {
        "runtime.price_fetch.providers.active": ["primary"],
        "runtime.price_fetch.providers.fallback": ["fallback"],
        "runtime.price_fetch.providers.deprecated": [],
    }
    adapter = MarketDataAdapter(
        config_getter=lambda k, d=None: cfg.get(k, d),
        providers={
            "primary": lambda _symbols: {},
            "fallback": lambda _symbols: {},
        },
    )

    out = adapter.quote_many(["NVDA"])
    assert out == {}
    assert adapter.last_meta.attempted == ["primary", "fallback"]
    assert adapter.last_meta.failed == ["primary", "fallback"]
    assert adapter.last_meta.succeeded == []
    assert adapter.last_meta.fallback_used is False
    assert adapter.last_meta.fallback_reason == "NO_PRICE_RESOLVED"
