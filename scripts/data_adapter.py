#!/usr/bin/env python3
"""
Data Adapter - 模拟新闻与市场数据接入
"""

from datetime import datetime
from typing import Dict, Any

try:
    from edt_module_base import CacheManager
except Exception:
    CacheManager = None


class DataAdapter:
    """数据接入适配器（真实新闻流优先 + 模拟兜底）"""

    def __init__(self):
        self.cache = CacheManager() if CacheManager else None

    def fetch_news(self) -> Dict[str, Any]:
        try:
            from ai_event_intel import NewsIngestion
        except Exception:
            NewsIngestion = None

        if NewsIngestion:
            out = NewsIngestion().run({"max_items": 1})
            if out.data.get("items"):
                item = out.data["items"][0]
                return {
                    "headline": item.get("headline", ""),
                    "source": item.get("source_url", ""),
                    "source_url": item.get("source_url", ""),
                    "source_type": item.get("source_type", ""),
                    "timestamp": item.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                    "raw_text": item.get("raw_text", ""),
                    "metadata": {
                        "keywords": [],
                        "region": "US",
                        "asset_class": ["equities", "bonds", "usd"],
                        "trace_id": item.get("trace_id"),
                    },
                }

        return {
            "headline": "Federal Reserve announces emergency rate cut of 50bps",
            "source": "https://www.federalreserve.gov/newsevents/2026/march/h1234567a.htm",
            "source_url": "https://www.federalreserve.gov/newsevents/2026/march/h1234567a.htm",
            "source_type": "official",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "raw_text": "The Federal Reserve has announced an emergency rate cut...",
            "metadata": {
                "keywords": ["Fed", "emergency", "rate cut"],
                "region": "US",
                "asset_class": ["equities", "bonds", "usd"],
                "trace_id": "TRC-FALLBACK-0001",
            }
        }

    def fetch_market_data(self) -> Dict[str, Any]:
        return {
            "vix_level": 35,
            "vix_change_pct": 45,
            "spx_change_pct": -2.8,
            "etf_volatility": {"change_pct": 3.2}
        }

    def fetch(self) -> Dict[str, Any]:
        key = "mock_event" 
        if self.cache:
            cached = self.cache.run({"action": "get", "key": key}).data
            if cached.get("hit"):
                return cached.get("value")

        payload = {
            "news": self.fetch_news(),
            "market_data": self.fetch_market_data()
        }

        if self.cache:
            self.cache.run({"action": "set", "key": key, "value": payload, "ttl_seconds": 300})
        return payload


if __name__ == "__main__":
    adapter = DataAdapter()
    data = adapter.fetch()
    print("DataAdapter OK")
    print(data)
