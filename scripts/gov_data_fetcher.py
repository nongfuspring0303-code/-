#!/usr/bin/env python3
"""
美国政府数据统一获取器（精简版：保留板块ETF获取方式）
来源：用户提供脚本 gov_data_fetcher
"""

import time
from datetime import datetime
from typing import Dict, Optional, Any
import requests

API_KEYS = {
    "twelvedata": "7144c3286d03404c8cd486b30c2af91a",
}


class BaseFetcher:
    def __init__(self, name: str):
        self.name = name
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "QuantTrade/1.0"})

    def _get(self, url: str, params: Dict = None) -> Optional[Dict]:
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None


class SectorETFFetcher(BaseFetcher):
    """板块 ETF 数据获取器 - 使用 TwelveData API"""

    BASE_URL = "https://api.twelvedata.com/time_series"

    SECTOR_ETF = {
        "XLF": {"name": "金融", "name_en": "Financials"},
        "XLK": {"name": "科技", "name_en": "Technology"},
        "XLE": {"name": "能源", "name_en": "Energy"},
        "XLV": {"name": "医疗", "name_en": "Healthcare"},
        "XLP": {"name": "消费必需品", "name_en": "Consumer Staples"},
        "XLI": {"name": "工业", "name_en": "Industrials"},
        "XLU": {"name": "公用事业", "name_en": "Utilities"},
        "XLB": {"name": "原材料", "name_en": "Materials"},
        "XLRE": {"name": "房地产", "name_en": "Real Estate"},
        "XLC": {"name": "通信", "name_en": "Communication"},
        "IWM": {"name": "小盘股", "name_en": "Russell 2000"},
        "IWD": {"name": "大盘价值", "name_en": "Large Cap Value"},
        "IWF": {"name": "大盘成长", "name_en": "Large Cap Growth"},
        "GLD": {"name": "黄金", "name_en": "Gold"},
        "SLV": {"name": "白银", "name_en": "Silver"},
        "TLT": {"name": "20年国债", "name_en": "20+ Year Treasury"},
        "HYG": {"name": "高收益债", "name_en": "High Yield Bond"},
        "VXX": {"name": "波动率", "name_en": "Volatility"},
    }

    def __init__(self):
        super().__init__("SectorETF")
        self.api_key = API_KEYS.get("twelvedata", "")

    def get_etf_quote(self, symbol: str) -> Optional[Dict]:
        if not self.api_key:
            return {"error": "TwelveData API Key 未配置"}
        params = {"symbol": symbol, "interval": "1day", "outputsize": 2, "apikey": self.api_key}
        data = self._get(self.BASE_URL, params)
        if data and data.get("status") == "ok" and "values" in data:
            values = data["values"]
            price = float(values[0]["close"]) if values else 0
            prev = float(values[1]["close"]) if len(values) > 1 else price
            change_pct = ((price - prev) / prev * 100) if prev else 0
            etf_info = self.SECTOR_ETF.get(symbol, {})
            return {
                "symbol": symbol,
                "name": etf_info.get("name", ""),
                "name_en": etf_info.get("name_en", ""),
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "date": values[0].get("datetime", "") if values else "",
            }
        if data and "message" in data:
            return {"error": data["message"]}
        return None

    def get_all_sectors(self) -> Dict[str, Any]:
        results = []
        for symbol in self.SECTOR_ETF.keys():
            item = self.get_etf_quote(symbol)
            if item and "error" not in item:
                results.append(item)
            time.sleep(0.3)
        return {"timestamp": datetime.now().isoformat(), "sectors": results}
