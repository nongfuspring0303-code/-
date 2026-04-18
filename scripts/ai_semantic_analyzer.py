#!/usr/bin/env python3
"""Feature-flagged semantic analyzer with GLM-4.7 Flash API support."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests

from config_center import ConfigCenter

ZAI_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


class SemanticAnalyzer:
    ALLOWED_EVENT_TYPES = {
        "tariff",
        "geo_political",
        "earnings",
        "monetary",
        "energy",
        "shipping",
        "industrial",
        "tech",
        "healthcare",
        "regulatory",
        "merger",
        "inflation",
        "commodity",
        "credit",
        "natural_disaster",
        "pandemic",
        "other",
    }

    def __init__(self, config_path: str | None = None):
        self.config = ConfigCenter(config_path=config_path)
        self.project_root = Path(__file__).resolve().parent.parent
        self._dotenv_local = self._load_dotenv_local()
        self.model_name = self._model_name() or "glm-4.7-flash"
        self._openai_endpoint_cache = ""

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

    def _load_dotenv_local(self) -> Dict[str, str]:
        """Load project .env.local dynamically on startup."""
        env_local = self.project_root / ".env.local"
        values: Dict[str, str] = {}
        if not env_local.exists():
            return values
        try:
            with env_local.open(encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    k = key.strip()
                    v = value.strip().strip('"').strip("'")
                    if not k:
                        continue
                    values[k] = v
                    os.environ.setdefault(k, v)
        except OSError:
            return {}
        return values

    def _get_env(self, key: str, default: str = "") -> str:
        value = os.getenv(key, "")
        if value:
            return value
        return self._dotenv_local.get(key, default)

    @staticmethod
    def _normalize_model_name(model: str) -> str:
        raw = str(model or "").strip()
        if "/" in raw:
            return raw.split("/")[-1]
        return raw

    def _openclaw_auth_profiles_path(self) -> Path:
        default_path = "/Users/workmac/.openclaw/agents/main/agent/auth-profiles.json"
        configured = self._get_env("OPENCLAW_AUTH_PROFILES", default_path)
        return Path(configured).expanduser()

    def _read_openclaw_profile(self, profile_key: str = "openai-codex:default") -> Dict[str, Any]:
        path = self._openclaw_auth_profiles_path()
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        profiles = payload.get("profiles", {})
        profile = profiles.get(profile_key, {}) if isinstance(profiles, dict) else {}
        return profile if isinstance(profile, dict) else {}

    def _openclaw_oauth_access(self) -> str:
        profile = self._read_openclaw_profile()
        access = str(profile.get("access", "") or "")
        expires = profile.get("expires")
        if not access:
            return ""
        if isinstance(expires, (int, float)) and expires > 0:
            if int(expires) <= int(time.time() * 1000):
                return ""
        return access

    def _openclaw_account_id(self) -> str:
        profile = self._read_openclaw_profile()
        return str(profile.get("accountId", "") or "")

    def _gateway_token_from_openclaw_config(self) -> str:
        config_path = Path(self._get_env("OPENCLAW_CONFIG", "/Users/workmac/.openclaw/openclaw.json")).expanduser()
        if not config_path.exists():
            return ""
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        gateway = data.get("gateway", {}) if isinstance(data, dict) else {}
        auth = gateway.get("auth", {}) if isinstance(gateway, dict) else {}
        return str(auth.get("token", "") or "")

    def _gateway_token(self) -> str:
        env_token = self._get_env("OPENCLAW_GATEWAY_TOKEN", "")
        if env_token:
            return env_token
        return self._gateway_token_from_openclaw_config()

    def _openai_base_url(self) -> str:
        # Requirement: dynamically load OPENAI_BASE_URL from project .env.local
        base = self._get_env("OPENAI_BASE_URL", "").strip()
        if base:
            return base.rstrip("/")
        # Default to local OpenClaw gateway first.
        return "http://127.0.0.1:18789"

    def _is_openclaw_gateway_base(self, base_url: str) -> bool:
        lower = str(base_url or "").lower()
        return (
            "127.0.0.1:18789" in lower
            or "localhost:18789" in lower
            or "openclaw.local:18789" in lower
        )

    def _openai_endpoint_candidates(self) -> List[str]:
        base = self._openai_base_url().rstrip("/")
        candidates: List[str] = []

        if base.endswith("/v1"):
            root = base[:-3].rstrip("/")
            candidates.extend(
                [
                    f"{base}/chat/completions",
                    f"{root}/v1/chat/completions",
                    f"{root}/openai/v1/chat/completions",
                    f"{root}/api/v1/chat/completions",
                ]
            )
        else:
            candidates.extend(
                [
                    f"{base}/v1/chat/completions",
                    f"{base}/chat/completions",
                    f"{base}/openai/v1/chat/completions",
                    f"{base}/api/v1/chat/completions",
                ]
            )

        unique: List[str] = []
        for item in candidates:
            if item not in unique:
                unique.append(item)
        return unique

    def _api_key(self) -> str:
        # Priority: env > .env.local > (none)
        # OAuth Support: If provider is OAuth-based, this returns the Client Secret or specific key
        provider = self._provider_name().lower()

        env_names = []
        if "openai" in provider:
            env_names = ["OPENAI_API_KEY"]
        
        cfg_env = str(self._semantic_cfg().get("api_key_env") or "")
        if cfg_env:
            env_names.insert(0, cfg_env)
        
        # Default back to ZAI if nothing else specified
        if not env_names:
            env_names = ["ZAI_API_KEY"]

        # 1. Environment variables
        for env_name in env_names:
            value = self._get_env(env_name, "").strip()
            if value:
                return value
        return ""

    def _abstain_response(
        self,
        *,
        fallback_reason: str,
        provider: str,
        model: str = "",
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
            "model": str(model or self.model_name or ""),
            "semantic_status": "fallback",
            "latency_ms": int(max(0, latency_ms)),
            "fallback_reason": fallback_reason,
            "a0_event_strength": 0,
            "expectation_gap": 0,
            "event_state": "Initial",
            "transmission_candidates": [],
            "evidence_spans": [],
            "risk_flags": [fallback_reason] if fallback_reason else [],
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
            "event_type": self._normalize_event_type(payload.get("event_type", "other")),
            "sentiment": str(payload.get("sentiment", "neutral") or "neutral"),
            "confidence": confidence,
            "recommended_chain": str(payload.get("recommended_chain", "") or ""),
            "recommended_stocks": payload.get("recommended_stocks", []),
            "verdict": "abstain",
            "reason": str(payload.get("reason", "") or ""),
            "provider": str(payload.get("provider", provider) or provider),
            "model": str(payload.get("model", self.model_name) or self.model_name),
            "semantic_status": str(payload.get("semantic_status", "") or ""),
            "latency_ms": int(max(0, parsed_latency)),
            "fallback_reason": str(payload.get("fallback_reason", "") or ""),
            "a0_event_strength": self._clamp_int(payload.get("a0_event_strength", confidence), 0, 100, confidence),
            "expectation_gap": self._clamp_int(payload.get("expectation_gap", 0), -100, 100, 0),
            "event_state": self._normalize_event_state(payload.get("event_state") or payload.get("narrative_stage"), ""),
            "transmission_candidates": payload.get("transmission_candidates", []),
            "evidence_spans": payload.get("evidence_spans", []),
            "risk_flags": payload.get("risk_flags", []),
        }
        if not isinstance(output["transmission_candidates"], list):
            output["transmission_candidates"] = []
        output["transmission_candidates"] = [str(x) for x in output["transmission_candidates"] if str(x).strip()][:3]
        if not isinstance(output["evidence_spans"], list):
            output["evidence_spans"] = []
        output["evidence_spans"] = [str(x) for x in output["evidence_spans"] if str(x).strip()][:3]
        if not isinstance(output["risk_flags"], list):
            output["risk_flags"] = []
        output["risk_flags"] = [str(x) for x in output["risk_flags"] if str(x).strip()]
        return output

    @classmethod
    def _normalize_event_type(cls, raw_type: Any) -> str:
        event_type = str(raw_type or "").strip().lower()
        return event_type if event_type in cls.ALLOWED_EVENT_TYPES else "other"

    @staticmethod
    def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = default
        return max(low, min(high, parsed))

    @staticmethod
    def _normalize_event_state(raw_state: Any, text: str) -> str:
        mapping = {
            "initial": "Initial",
            "developing": "Developing",
            "peak": "Peak",
            "fading": "Fading",
            "dead": "Dead",
            "continuation": "Developing",
            "exhaustion": "Peak",
        }
        state = str(raw_state or "").strip().lower()
        if state in mapping:
            return mapping[state]
        lower = text.lower()
        if any(k in lower for k in ["resolved", "cancelled", "辟谣", "失效", "终止"]):
            return "Dead"
        if any(k in lower for k in ["surge", "spike", "高潮", "拥挤"]):
            return "Peak"
        if any(k in lower for k in ["cooling", "回落", "衰退", "fading"]):
            return "Fading"
        return "Initial"

    @staticmethod
    def _event_strength(confidence: int, verdict: str) -> int:
        boost = 8 if verdict == "hit" else -12
        return max(0, min(100, confidence + boost))

    @staticmethod
    def _expectation_gap(sentiment: str, confidence: int, headline: str) -> int:
        sign = 0
        s = str(sentiment or "").lower()
        if s == "positive":
            sign = 1
        elif s == "negative":
            sign = -1
        base = max(0, min(100, confidence))
        text = (headline or "").lower()
        if any(k in text for k in ["unexpected", "surprise", "超预期", "意外", "unexpectedly"]):
            base = min(100, base + 10)
        return int(sign * base)

    @staticmethod
    def _evidence_spans(headline: str, raw_text: str) -> List[str]:
        spans: List[str] = []
        if headline:
            spans.append(str(headline).strip())
        for chunk in str(raw_text or "").replace("\n", " ").split("."):
            piece = chunk.strip()
            if len(piece) >= 18:
                spans.append(piece)
            if len(spans) >= 3:
                break
        return spans[:3]

    @staticmethod
    def _transmission_candidates(event_type: str, sentiment: str) -> List[str]:
        et = str(event_type or "").lower()
        s = str(sentiment or "").lower()
        if et in {"tariff", "trade_talks"}:
            return ["import_cost", "export_margin", "supply_chain"]
        if et in {"monetary", "inflation"}:
            return ["real_rate", "usd_liquidity", "duration_asset"]
        if et in {"energy", "geo_political"}:
            return ["oil_price", "shipping_cost", "defense_demand"]
        if s == "positive":
            return ["risk_appetite", "sector_rotation", "leader_momentum"]
        if s == "negative":
            return ["risk_aversion", "valuation_compression", "liquidity_tightening"]
        return ["market_attention", "headline_sensitivity"]

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

        provider_lower = provider.lower()
        if "openai" in provider_lower or "gpt" in model.lower():
            return self._call_openai_api(text, timeout_ms, model=model)

        if provider_lower in ("glm_4", "glm-4.7-flash", "glm-4.7", "glm-4-flash", "gemini_flash_lite") or "glm" in model.lower():
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
    @staticmethod
    def _safe_json(response: requests.Response) -> Dict[str, Any]:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    @staticmethod
    def _extract_openai_error(response: requests.Response) -> str:
        payload = SemanticAnalyzer._safe_json(response)
        error = payload.get("error", {})
        if isinstance(error, dict):
            message = str(error.get("message", "") or "")
            code = str(error.get("code", "") or "")
            if code and message:
                return f"{code}: {message}"
            if message:
                return message
            if code:
                return code
        text = (response.text or "").strip()
        return text[:200] if text else f"status_{response.status_code}"

    def _post_openai_with_candidates(
        self,
        *,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout_seconds: float,
    ) -> Tuple[requests.Response | None, str, str]:
        candidates = self._openai_endpoint_candidates()
        if self._openai_endpoint_cache and self._openai_endpoint_cache in candidates:
            candidates = [self._openai_endpoint_cache] + [c for c in candidates if c != self._openai_endpoint_cache]

        last_error = ""
        last_response: requests.Response | None = None
        for endpoint in candidates:
            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout_seconds)
            except requests.RequestException as exc:
                last_error = str(exc)
                continue

            last_response = response
            if response.status_code == 404:
                last_error = "endpoint_not_found"
                continue

            self._openai_endpoint_cache = endpoint
            return response, endpoint, ""

        return last_response, "", last_error or "openai_endpoint_not_found"

    def _call_openai_api(self, text: str, timeout_ms: int, *, model: str = "") -> Dict[str, Any]:
        prompt = self._get_prompt(text)
        # Normalize Codex model id: "openai-codex/gpt-5.3-codex" -> "gpt-5.3-codex"
        use_model = self._normalize_model_name(model or self.model_name or "gpt-5.3-codex")
        base_url = self._openai_base_url()

        # Auth sources:
        # 1) OpenClaw OAuth profile token (required by your workflow)
        # 2) OPENAI_API_KEY fallback when profile token is missing/expired
        profile_token = self._openclaw_oauth_access()
        api_key_fallback = self._api_key()
        gateway_token = self._gateway_token()
        account_id = self._openclaw_account_id()

        via_gateway = self._is_openclaw_gateway_base(base_url) and bool(gateway_token)
        auth_token = gateway_token if via_gateway else (profile_token or api_key_fallback)
        if not auth_token:
            return self._abstain_response(fallback_reason="openai_auth_missing", provider="openai", model=use_model)

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }
        if gateway_token:
            headers["X-Claw-Token"] = gateway_token
        if account_id:
            headers["X-OpenClaw-Account-Id"] = account_id

        # OpenClaw OpenAI-compatible endpoint requires model=openclaw or openclaw/<agentId>.
        transport_model = "openclaw" if via_gateway else use_model
        payload: Dict[str, Any] = {
            "model": transport_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 300,
        }
        if "gpt-4" in use_model or "gpt-5" in use_model or "gpt-3.5-turbo-0125" in use_model:
            payload["response_format"] = {"type": "json_object"}

        timeout_seconds = max(5.0, timeout_ms / 1000.0)
        response, endpoint, route_error = self._post_openai_with_candidates(
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        if response is None:
            return self._abstain_response(
                fallback_reason=f"openai_route_error:{route_error[:80]}",
                provider="openai",
                model=use_model,
            )

        # Fallback: if profile token fails auth, retry once with explicit API key.
        if (
            not via_gateway
            and response.status_code in (401, 403)
            and profile_token
            and api_key_fallback
            and api_key_fallback != profile_token
        ):
            retry_headers = dict(headers)
            retry_headers["Authorization"] = f"Bearer {api_key_fallback}"
            response, endpoint, route_error = self._post_openai_with_candidates(
                headers=retry_headers,
                payload=payload,
                timeout_seconds=timeout_seconds,
            )
            if response is None:
                return self._abstain_response(
                    fallback_reason=f"openai_route_error:{route_error[:80]}",
                    provider="openai",
                    model=use_model,
                )

        # Recovery: some gateways are strict and reject non-openclaw model values.
        if response.status_code == 400 and transport_model != "openclaw":
            parsed_error = self._extract_openai_error(response).lower()
            if "invalid `model`" in parsed_error and "use `openclaw`" in parsed_error:
                retry_payload = dict(payload)
                retry_payload["model"] = "openclaw"
                response, endpoint, route_error = self._post_openai_with_candidates(
                    headers=headers,
                    payload=retry_payload,
                    timeout_seconds=timeout_seconds,
                )
                if response is None:
                    return self._abstain_response(
                        fallback_reason=f"openai_route_error:{route_error[:80]}",
                        provider="openai",
                        model=use_model,
                    )

        if response.status_code >= 400:
            reason = self._extract_openai_error(response)
            return self._abstain_response(
                fallback_reason=f"openai_http_{response.status_code}:{reason[:120]}",
                provider="openai",
                model=use_model,
            )

        result = self._safe_json(response)
        choices = result.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return self._abstain_response(fallback_reason="openai_no_choices", provider="openai", model=use_model)
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = str(message.get("content", "") or "").strip()
        if not content:
            return self._abstain_response(fallback_reason="openai_empty_content", provider="openai", model=use_model)
        parsed = self._parse_ai_content(content)
        parsed["provider"] = "openai"
        parsed["model"] = use_model
        parsed["reason"] = str(parsed.get("reason", "") or f"openai response via {endpoint}")
        return parsed

    def _get_prompt(self, text: str) -> str:
        return f"""You are an Event Object extractor for an event-driven trading system.

STRICT OUTPUT CONTRACT:
- Return ONE JSON object only. No markdown, no prose.
- Required fields:
  - event_type: one of [tariff, geo_political, earnings, monetary, energy, shipping, industrial, tech, healthcare, regulatory, merger, inflation, commodity, credit, natural_disaster, pandemic, other]
  - sentiment: one of [positive, negative, neutral]
  - confidence: integer 0..100
  - a0_event_strength: integer 0..100
  - expectation_gap: integer -100..100
  - event_state: one of [Initial, Developing, Peak, Fading, Dead]
  - transmission_candidates: array of short strings, 0..3 items
  - evidence_spans: array of short source snippets, 1..3 items
  - risk_flags: array of strings
  - reason: short sentence

News text:
{text}
"""

    def _parse_ai_content(self, content: str) -> Dict[str, Any]:
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        if clean_content.startswith("```"):
            clean_content = clean_content[3:]
        
        try:
            parsed = json.loads(clean_content.strip())
            return {
                "event_type": self._normalize_event_type(parsed.get("event_type", "other")),
                "sentiment": parsed.get("sentiment", "neutral"),
                "confidence": parsed.get("confidence", 50),
                "recommended_chain": parsed.get("recommended_chain", ""),
                "recommended_stocks": parsed.get("recommended_stocks", []),
                "a0_event_strength": parsed.get("a0_event_strength", parsed.get("confidence", 50)),
                "expectation_gap": parsed.get("expectation_gap", 0),
                "event_state": parsed.get("event_state", "Initial"),
                "transmission_candidates": parsed.get("transmission_candidates", []),
                "evidence_spans": parsed.get("evidence_spans", []),
                "risk_flags": parsed.get("risk_flags", []),
                "reason": parsed.get("reason", "success"),
            }
        except:
             return self._abstain_response(fallback_reason="json_parse_failed", provider="ai")

    def _call_glm_api(self, text: str, timeout_ms: int, *, model: str = "") -> Dict[str, Any]:
        prompt = self._get_prompt(text)
        api_key = self._api_key()
        if not api_key:
            return self._abstain_response(
                fallback_reason="api_key_missing",
                provider=self._provider_name(),
                model=model or self.model_name,
            )

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model or self.model_name,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 200,
            }
            timeout_seconds = max(5.0, timeout_ms / 1000.0)
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
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                if content.startswith("```"):
                    content = content[3:]
                content = content.strip()
                try:
                    parsed = json.loads(content)
                    return {
                        "event_type": self._normalize_event_type(parsed.get("event_type", "other")),
                        "sentiment": parsed.get("sentiment", "neutral"),
                        "confidence": parsed.get("confidence", 50),
                        "recommended_chain": parsed.get("recommended_chain", ""),
                        "recommended_stocks": parsed.get("recommended_stocks", []),
                        "a0_event_strength": parsed.get("a0_event_strength", parsed.get("confidence", 50)),
                        "expectation_gap": parsed.get("expectation_gap", 0),
                        "event_state": parsed.get("event_state", parsed.get("narrative_stage", "Initial")),
                        "transmission_candidates": parsed.get("transmission_candidates", []),
                        "evidence_spans": parsed.get("evidence_spans", []),
                        "risk_flags": parsed.get("risk_flags", []),
                        "reason": parsed.get("reason", f"{self.model_name} api response"),
                    }
                except json.JSONDecodeError:
                    return {
                        "event_type": "other",
                        "sentiment": "neutral",
                        "confidence": 50,
                        "recommended_chain": "",
                        "recommended_stocks": [],
                        "reason": f"{self.model_name} response parsing failed: {content[:200]}",
                    }

            return {
                "event_type": "other",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": f"{self.model_name} no choices returned",
            }

        except requests.exceptions.Timeout:
            return {
                "event_type": "other",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": f"{self.model_name} timeout",
            }
        except requests.exceptions.RequestException as e:
            return {
                "event_type": "other",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": f"{self.model_name} API error: {str(e)[:100]}",
            }
        except Exception as e:
            return {
                "event_type": "other",
                "sentiment": "neutral",
                "confidence": 50,
                "recommended_chain": "",
                "recommended_stocks": [],
                "reason": f"{self.model_name} error: {str(e)[:100]}",
            }

    def analyze(self, headline: str, raw_text: str = "") -> Dict[str, Any]:
        provider = self._provider_name()
        model = self._model_name()
        timeout_ms = self._timeout_ms()

        if not self._enabled():
            out = self._abstain_response(
                fallback_reason="semantic_disabled",
                provider=provider,
                model=model,
            )
            out.update(self.analyze_event(headline, raw_text))
            return out

        if self._emergency_disabled():
            out = self._abstain_response(
                fallback_reason="emergency_disabled",
                provider=provider,
                model=model,
            )
            out.update(self.analyze_event(headline, raw_text))
            return out

        if not self._full_enabled():
            out = self._abstain_response(
                fallback_reason="full_enable_disabled",
                provider=provider,
                model=model,
            )
            out.update(self.analyze_event(headline, raw_text))
            return out

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
            out = self._abstain_response(
                fallback_reason="timeout",
                provider=provider,
                model=model,
                latency_ms=elapsed,
            )
            out.update(self.analyze_event(headline, raw_text))
            return out
        except Exception:
            elapsed = int((time.perf_counter() - started) * 1000.0)
            out = self._abstain_response(
                fallback_reason="provider_error",
                provider=provider,
                model=model,
                latency_ms=elapsed,
            )
            out.update(self.analyze_event(headline, raw_text))
            return out

        elapsed = int((time.perf_counter() - started) * 1000.0)
        out = self._coerce_output(payload if isinstance(payload, dict) else {}, provider, elapsed)

        if out["confidence"] < self._min_confidence():
            out["verdict"] = "abstain"
            out["semantic_status"] = "fallback"
            if not out.get("fallback_reason"):
                out["fallback_reason"] = "confidence_below_threshold"
            if not out["reason"]:
                out["reason"] = "confidence below threshold"
            out.update(self.analyze_event(headline, raw_text, semantic_output=out))
            return out

        if out["recommended_chain"] or out.get("transmission_candidates"):
            out["verdict"] = "hit"
            out["semantic_status"] = "hit"
            if not out["reason"]:
                out["reason"] = "semantic hit"
            if not out.get("fallback_reason"):
                out["fallback_reason"] = ""
            out.update(self.analyze_event(headline, raw_text, semantic_output=out))
            return out

        out["verdict"] = "abstain"
        out["semantic_status"] = "fallback"
        if not out.get("fallback_reason"):
            out["fallback_reason"] = "chain_missing"
        if not out["reason"]:
            out["reason"] = "missing recommended chain"
        out.update(self.analyze_event(headline, raw_text, semantic_output=out))
        return out

    def analyze_event(
        self,
        headline: str,
        raw_text: str = "",
        *,
        semantic_output: Dict[str, Any] | None = None,
        event_id: str = "",
        event_time: str = "",
    ) -> Dict[str, Any]:
        """Build contract-style EventObject for downstream rule systems."""
        semantic = semantic_output if isinstance(semantic_output, dict) else {}
        confidence = self._clamp_int(semantic.get("confidence", 0), 0, 100, 0)
        sentiment = str(semantic.get("sentiment", "neutral"))
        event_type = self._normalize_event_type(semantic.get("event_type", "other"))
        state = self._normalize_event_state(
            semantic.get("event_state") or semantic.get("narrative_stage"),
            f"{headline} {raw_text}",
        )
        verdict = str(semantic.get("verdict", "abstain"))
        fallback_reason = str(semantic.get("fallback_reason", "") or "")
        semantic_candidates = semantic.get("transmission_candidates", [])
        if not isinstance(semantic_candidates, list):
            semantic_candidates = []
        normalized_candidates = [str(x) for x in semantic_candidates if str(x).strip()][:3]

        generated_event_time = event_time
        if not generated_event_time:
            generated_event_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        evidence_grade = "C"
        if confidence >= 85:
            evidence_grade = "A"
        elif confidence >= 70:
            evidence_grade = "B"
        elif confidence >= 55:
            evidence_grade = "B-"

        risk_flags: List[str] = []
        if fallback_reason:
            risk_flags.append(fallback_reason)
        if verdict != "hit":
            risk_flags.append("semantic_not_hit")

        return {
            "event_id": str(event_id or ""),
            "event_type": event_type,
            "event_time": generated_event_time,
            "a0_event_strength": self._event_strength(confidence, verdict),
            "expectation_gap": self._expectation_gap(sentiment, confidence, headline),
            "event_state": state,
            "transmission_candidates": normalized_candidates or self._transmission_candidates(event_type, sentiment)[:3],
            "evidence_grade": evidence_grade,
            "evidence_spans": self._evidence_spans(headline, raw_text),
            "risk_flags": risk_flags,
        }
