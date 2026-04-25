#!/usr/bin/env python3
"""
Stage-4 MarketDataAdapter

R-S4-001: 统一 provider 入口（active/fallback/deprecated）
R-S4-002: 支持 batch 抓价与内存 cache
R-S4-003: provider failover（active 失败后自动尝试 fallback）
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional runtime dependency
    yf = None


@dataclass
class FetchMeta:
    provider_chain: List[str]
    attempted: List[str]
    succeeded: List[str]
    unresolved_symbols: List[str]
    from_cache: int
    failed: List[str]
    failure_reasons: Dict[str, str]
    fallback_used: bool
    fallback_reason: str


class MarketDataAdapter:
    def __init__(
        self,
        config_getter: Optional[Callable[[str, Any], Any]] = None,
        providers: Optional[Dict[str, Callable[[List[str]], Dict[str, float]]]] = None,
        now_fn: Optional[Callable[[], float]] = None,
    ):
        self._get = config_getter or (lambda _k, default=None: default)
        self._now = now_fn or time.time
        self._cache: Dict[str, Dict[str, float]] = {}
        self._last_meta = FetchMeta([], [], [], [], 0, [], {}, False, "")

        self.cache_ttl_seconds = self._safe_int(self._get("runtime.price_fetch.cache_ttl_seconds", 120), 120)
        self.max_batch_size = self._safe_int(self._get("runtime.price_fetch.max_batch_size", 40), 40)
        self.timeout_seconds = self._safe_int(self._get("runtime.price_fetch.timeout_seconds", 5), 5)

        active = self._coerce_str_list(self._get("runtime.price_fetch.providers.active", ["yahoo"]))
        fallback = self._coerce_str_list(self._get("runtime.price_fetch.providers.fallback", ["stooq"]))
        deprecated = set(self._coerce_str_list(self._get("runtime.price_fetch.providers.deprecated", [])))
        self.active_providers = list(active)
        self.fallback_providers = list(fallback)

        chain = [p for p in active + fallback if p not in deprecated]
        # No implicit provider fallback when config explicitly clears the chain.
        # This preserves config-runtime alignment for disable/deprecated scenarios.
        self.provider_chain = chain

        self.providers = {
            "yahoo": self._fetch_yahoo,
            "stooq": self._fetch_stooq,
        }
        if providers:
            self.providers.update(providers)

    @property
    def last_meta(self) -> FetchMeta:
        return self._last_meta

    def quote_one(self, symbol: str) -> Optional[float]:
        out = self.quote_many([symbol])
        return out.get(symbol.upper().strip())

    def quote_many(self, symbols: Iterable[str]) -> Dict[str, float]:
        normalized = [str(s).upper().strip() for s in symbols if str(s).strip()]
        if not normalized:
            self._last_meta = FetchMeta(self.provider_chain, [], [], [], 0, [], {}, False, "")
            return {}

        now = self._now()
        resolved: Dict[str, float] = {}
        unresolved: List[str] = []
        cache_hits = 0

        for symbol in normalized:
            cached = self._cache.get(symbol)
            if cached and now - cached.get("ts", 0.0) < self.cache_ttl_seconds:
                resolved[symbol] = float(cached["price"])
                cache_hits += 1
            else:
                unresolved.append(symbol)

        attempted: List[str] = []
        succeeded: List[str] = []
        failed: List[str] = []
        failure_reasons: Dict[str, str] = {}

        for provider_name in self.provider_chain:
            if not unresolved:
                break
            provider_fn = self.providers.get(provider_name)
            if provider_fn is None:
                continue
            attempted.append(provider_name)

            fresh: Dict[str, float] = {}
            provider_reason = ""
            for batch in self._chunked(unresolved, self.max_batch_size):
                try:
                    fetched = provider_fn(batch)
                except Exception as exc:  # pragma: no cover - defensive runtime guard
                    fetched = {}
                    provider_reason = f"exception:{type(exc).__name__}"
                for sym, px in fetched.items():
                    if sym in unresolved and px is not None and float(px) > 0:
                        fresh[sym] = float(px)

            if fresh:
                succeeded.append(provider_name)
                for sym, px in fresh.items():
                    resolved[sym] = px
                    self._cache[sym] = {"price": px, "ts": now}
                unresolved = [sym for sym in unresolved if sym not in fresh]
            else:
                failed.append(provider_name)
                failure_reasons[provider_name] = provider_reason or "empty_response"

        fallback_used = any(name in self.fallback_providers for name in succeeded)
        fallback_reason = ""
        if unresolved:
            if not succeeded:
                fallback_reason = "NO_PRICE_RESOLVED"
            elif fallback_used:
                fallback_reason = "FALLBACK_PARTIAL"
            else:
                fallback_reason = "PARTIAL_PRICE_RESOLVED"

        self._last_meta = FetchMeta(
            provider_chain=list(self.provider_chain),
            attempted=attempted,
            succeeded=succeeded,
            unresolved_symbols=list(unresolved),
            from_cache=cache_hits,
            failed=failed,
            failure_reasons=failure_reasons,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
        return resolved

    def _fetch_yahoo(self, symbols: List[str]) -> Dict[str, float]:
        if not symbols:
            return {}

        # Prefer yfinance first to avoid Yahoo HTTP quote auth/cookie fragility.
        if yf is not None:
            out_yf: Dict[str, float] = {}
            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    fast = getattr(ticker, "fast_info", {}) or {}
                    price = (
                        fast.get("lastPrice")
                        or fast.get("last_price")
                        or fast.get("regularMarketPrice")
                    )
                    if price is not None and float(price) > 0:
                        out_yf[symbol.upper().strip()] = float(price)
                except Exception:
                    continue
            if out_yf:
                return out_yf

        base = str(self._get("runtime.price_fetch.yahoo_quote_base", "https://query1.finance.yahoo.com/v7/finance/quote?symbols=")).strip()
        joined = ",".join(symbols)
        url = f"{base}{urllib.parse.quote(joined)}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            result = ((payload.get("quoteResponse") or {}).get("result") or [])
            out: Dict[str, float] = {}
            for row in result:
                symbol = str(row.get("symbol", "")).upper().strip()
                price = row.get("regularMarketPrice")
                if symbol and price is not None:
                    out[symbol] = float(price)
            return out
        except Exception:
            return {}

    def _fetch_stooq(self, symbols: List[str]) -> Dict[str, float]:
        # 轻量 fallback：逐 symbol 请求，避免引入额外依赖。
        out: Dict[str, float] = {}
        for symbol in symbols:
            url = f"https://stooq.com/q/l/?s={urllib.parse.quote(symbol.lower())}.us&i=d"
            try:
                with urllib.request.urlopen(url, timeout=self.timeout_seconds) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if len(lines) < 2:
                    continue
                # Symbol,Date,Time,Open,High,Low,Close,Volume
                cols = [c.strip() for c in lines[1].split(",")]
                if len(cols) >= 7 and cols[6] not in {"", "N/D"}:
                    close = float(cols[6])
                    if close > 0:
                        out[symbol.upper()] = close
            except Exception:
                continue
        return out

    @staticmethod
    def _chunked(items: List[str], n: int) -> Iterable[List[str]]:
        size = max(1, int(n))
        for idx in range(0, len(items), size):
            yield items[idx: idx + size]

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except Exception:
            return default

    @staticmethod
    def _coerce_str_list(value: Any) -> List[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        out: List[str] = []
        for item in value:
            p = str(item).strip().lower()
            if p:
                out.append(p)
        return out
