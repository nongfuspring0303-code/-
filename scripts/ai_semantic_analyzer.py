#!/usr/bin/env python3
"""Feature-flagged semantic analyzer with GLM-4.7 Flash API support."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict

import requests
from config_center import ConfigCenter

ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"


class SemanticAnalyzer:
    def __init__(self, config_path: str | None = None):
        self.config = ConfigCenter(config_path=config_path)

    def _semantic_cfg(self) -> Dict[str, Any]:
        runtime = self.config.data.get("runtime", {}) if isinstance(self.config.data, dict) else {}
        semantic = runtime.get("semantic", {}) if isinstance(runtime, dict) else {}
        return semantic if isinstance(semantic, dict) else {}

    def _enabled(self) -> bool:
        return bool(self._semantic_cfg().get("enabled", False))

    def _emergency_disabled(self) -> bool:
        return bool(self._semantic_cfg().get("emergency_disable", False))

    def _full_enabled(self) -> bool:
        return bool(self._semantic_cfg().get("full_enable", True))

    def _min_confidence(self) -> int:
        value = self._semantic_cfg().get("min_confidence", 70)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 70
        return max(0, min(100, parsed))

    def _timeout_ms(self) -> int:
        value = self._semantic_cfg().get("timeout_ms", 3000)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 3000
        return max(1, parsed)

    def _provider_name(self) -> str:
        provider = self._semantic_cfg().get("provider", "deterministic")
        return str(provider or "deterministic")

    def _model_name(self) -> str:
        model = self._semantic_cfg().get("model", "")
        return str(model or "")

    def _api_key(self) -> str:
        semantic = self._semantic_cfg()
        env_name = str(semantic.get("api_key_env", "ZAI_API_KEY") or "ZAI_API_KEY").strip()
        env_names = [env_name, "GLM_API_KEY", "OPENCLAW_GLM_API_KEY"]
        for name in env_names:
            value = os.getenv(name, "").strip()
            if value:
                return value
        return ""

    def _abstain_response(
        self,
        *,
        fallback_reason: str,
        provider: str,
        latency_ms: int = 0,
    ) -> Dict[str, Any]:
        return {
            "event_type": "unknown",
            "sentiment": "neutral",
            "confidence": 0,
            "recommended_chain": "",
            "recommended_stocks": [],
            "verdict": "abstain",
            "reason": fallback_reason,
            "provider": provider,
            "latency_ms": int(max(0, latency_ms)),
            "fallback_reason": fallback_reason,
        }

    def _coerce_output(self, payload: Dict[str, Any], provider: str, latency_ms: int) -> Dict[str, Any]:
        try:
            confidence = int(float(payload.get("confidence", 0) or 0))
        except (TypeError, ValueError):
            confidence = 0
        confidence = max(0, min(100, confidence))

        try:
            parsed_latency = int(float(payload.get("latency_ms", latency_ms) or latency_ms))
        except (TypeError, ValueError):
            parsed_latency = latency_ms

        output = {
            "event_type": str(payload.get("event_type", "unknown") or "unknown"),
            "sentiment": str(payload.get("sentiment", "neutral") or "neutral"),
            "confidence": confidence,
            "recommended_chain": str(payload.get("recommended_chain", "") or ""),
            "recommended_stocks": payload.get("recommended_stocks", []),
            "verdict": "abstain",
            "reason": str(payload.get("reason", "") or ""),
            "provider": str(payload.get("provider", provider) or provider),
            "latency_ms": int(max(0, parsed_latency)),
            "fallback_reason": str(payload.get("fallback_reason", "") or ""),
        }
        return output

    def _call_provider(
        self,
        headline: str,
        raw_text: str,
        *,
        provider: str,
        model: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        text = f"{headline} {raw_text}"

        if provider in ("glm_4", "glm-4.7-flash", "glm-4.7", "gemini_flash_lite") or model:
            return self._call_glm_api(text, timeout_ms, model=model)

        text_lower = text.lower()
        if any(k in text_lower for k in ["trade meeting", "trade talks", "贸易会议", "贸易谈判", "谈判"]):
            return {
                "event_type": "trade_talks",
                "sentiment": "neutral",
                "confidence": 80,
                "recommended_chain": "trade_talks_chain",
                "recommended_stocks": [],
                "reason": "deterministic keyword match",
            }
        if any(k in text_lower for k in ["tariff", "trade war", "关税", "贸易战"]):
            return {
                "event_type": "tariff",
                "sentiment": "negative",
                "confidence": 82,
                "recommended_chain": "tariff_chain",
                "recommended_stocks": [],
                "reason": "deterministic keyword match",
            }
        return {
            "event_type": "unknown",
            "sentiment": "neutral",
            "confidence": 50,
            "recommended_chain": "",
            "recommended_stocks": [],
            "reason": "deterministic fallback",
        }

    def _call_glm_api(self, text: str, timeout_ms: int, *, model: str = "") -> Dict[str, Any]:
        prompt = f"""你是一个金融新闻语义分析专家。请分析以下新闻标题和内容，判断其是否可能触发交易机会。

新闻内容：{text}

请返回一个JSON格式的分析结果，包含以下字段：
- event_type: 事件类型（如：earnings, product_launch, regulatory, merger_acquisition, trade_talks, tariff, etc.）
- sentiment: 情绪（positive/negative/neutral）
- confidence: 置信度（0-100的整数）
- recommended_chain: 推荐的应对链名称（如果有）
- reason: 判断理由

event_type 可选：
- tariff: 关税、贸易战
- geo_political: 地缘政治、军事冲突
- earnings: 财报、业绩
- monetary: 央行、利率
- energy: 能源、油气
- shipping: 航运、海运
- industrial: 工业、制造
- tech: 科技
- healthcare: 医疗
- regulatory: 监管政策、法规
- merger: 并购、重组
- inflation: 通胀
- commodity: 大宗商品
- credit: 信用违约、债券
- natural_disaster: 自然灾害
- pandemic: 疫情、公共卫生
- other: 其他

confidence: 0-100
recommended_chain: 推荐的分析链（可选）
recommended_stocks: 推荐的股票列表（可选），格式为股票代码数组，如["NVDA","AAPL","MSFT"]

示例：
{{"event_type":"monetary","sentiment":"positive","confidence":90,"recommended_chain":"rate_cut_chain","recommended_stocks":["NVDA","AAPL"],"reason":"美联储降息，流动性宽松，利好科技股"}}

新闻：{text}

只返回JSON，不要解释。"""

        api_key = self._api_key()
        if not api_key:
            return {
                "event_type": "unknown",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": "glm-4.7-flash api key missing",
            }

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model or "glm-4.7-flash",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 500,
            }
            timeout_seconds = timeout_ms / 1000.0
            response = requests.post(
                f"{ZAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()

            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                try:
                    parsed = json.loads(content)
                    return {
                        "event_type": parsed.get("event_type", "unknown"),
                        "sentiment": parsed.get("sentiment", "neutral"),
                        "confidence": parsed.get("confidence", 50),
                        "recommended_chain": parsed.get("recommended_chain", ""),
                        "recommended_stocks": parsed.get("recommended_stocks", []),
                        "reason": parsed.get("reason", "glm-4.7-flash api response"),
                    }
                except json.JSONDecodeError:
                    return {
                        "event_type": "unknown",
                        "sentiment": "neutral",
                        "confidence": 50,
                        "recommended_chain": "",
                        "recommended_stocks": [],
                        "reason": f"glm-4.7-flash response parsing failed: {content[:200]}",
                    }

            return {
                "event_type": "unknown",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": "glm-4.7-flash no choices returned",
            }

        except requests.exceptions.Timeout:
            return {
                "event_type": "unknown",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": "glm-4.7-flash timeout",
            }
        except requests.exceptions.RequestException as e:
            return {
                "event_type": "unknown",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": f"glm-4.7-flash API error: {str(e)[:100]}",
            }
        except Exception as e:
            return {
                "event_type": "unknown",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": f"glm-4.7-flash error: {str(e)[:100]}",
            }

    def analyze(self, headline: str, raw_text: str = "") -> Dict[str, Any]:
        provider = self._provider_name()
        model = self._model_name()
        timeout_ms = self._timeout_ms()

        if not self._enabled():
            return self._abstain_response(
                fallback_reason="semantic_disabled",
                provider=provider,
            )

        if self._emergency_disabled():
            return self._abstain_response(
                fallback_reason="emergency_disabled",
                provider=provider,
            )

        if not self._full_enabled():
            return self._abstain_response(
                fallback_reason="full_enable_disabled",
                provider=provider,
            )

        started = time.perf_counter()
        try:
            payload = self._call_provider(
                headline,
                raw_text,
                provider=provider,
                model=model,
                timeout_ms=timeout_ms,
            )
        except TimeoutError:
            elapsed = int((time.perf_counter() - started) * 1000.0)
            return self._abstain_response(
                fallback_reason="timeout",
                provider=provider,
                latency_ms=elapsed,
            )
        except Exception:
            elapsed = int((time.perf_counter() - started) * 1000.0)
            return self._abstain_response(
                fallback_reason="provider_error",
                provider=provider,
                latency_ms=elapsed,
            )

        elapsed = int((time.perf_counter() - started) * 1000.0)
        out = self._coerce_output(payload if isinstance(payload, dict) else {}, provider, elapsed)

        if out["confidence"] < self._min_confidence():
            out["verdict"] = "abstain"
            out["fallback_reason"] = "confidence_below_threshold"
            if not out["reason"]:
                out["reason"] = "confidence below threshold"
            return out

        if out["recommended_chain"]:
            out["verdict"] = "hit"
            if not out["reason"]:
                out["reason"] = "semantic hit"
            out["fallback_reason"] = ""
            return out

        out["verdict"] = "abstain"
        out["fallback_reason"] = "chain_missing"
        if not out["reason"]:
            out["reason"] = "missing recommended chain"
        return out
