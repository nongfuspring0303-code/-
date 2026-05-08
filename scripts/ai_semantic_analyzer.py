#!/usr/bin/env python3
"""Feature-flagged semantic analyzer with GLM-4.7 Flash API support."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    PARSE_ERROR_TYPES = {
        "no_json_object",
        "invalid_json_syntax",
        "root_not_object",
        "schema_failed",
        "recommended_stocks_not_list",
        "provider_error",
        "timeout",
        "truncated_response",
        "empty_response",
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
        value = self._semantic_cfg().get("timeout_ms", 20000)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 20000
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

    def _openclaw_auth_profiles_path(self) -> Optional[Path]:
        configured = self._get_env("OPENCLAW_AUTH_PROFILES", "").strip()
        if not configured:
            return None
        return Path(configured).expanduser()

    def _read_openclaw_profile(self, profile_key: str = "openai-codex:default") -> Dict[str, Any]:
        path = self._openclaw_auth_profiles_path()
        if not path or not path.exists():
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
        configured = self._get_env("OPENCLAW_CONFIG", "").strip()
        if not configured:
            return ""
        config_path = Path(configured).expanduser()
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
        # No silent fallback to local gateway; raise if not configured.
        raise RuntimeError(
            "OPENAI_BASE_URL is not configured. Set it via env var or .env.local file."
        )

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

        # OpenClaw local gateway currently exposes the OpenAI-compatible route at /v1/chat/completions.
        # Restricting candidates here avoids deterministic 404 noise from legacy probe paths.
        if self._is_openclaw_gateway_base(base):
            if base.endswith("/v1"):
                return [f"{base}/chat/completions"]
            return [f"{base}/v1/chat/completions"]

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
        fallback_detail: str = "",
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
            "reason": fallback_detail or fallback_reason,
            "provider": provider,
            "model": str(model or self.model_name or ""),
            "semantic_status": "fallback",
            "latency_ms": int(max(0, latency_ms)),
            "fallback_reason": fallback_reason,
            "fallback_detail": str(fallback_detail or ""),
            "a0_event_strength": 0,
            "expectation_gap": 0,
            "event_state": "Initial",
            "transmission_candidates": [],
            "transmission_path": [],
            "entities": [],
            "narrative_vs_fact": "mixed",
            "event_scope": "Sector",
            "novelty_score": 0.0,
            "evidence_spans": [],
            "risk_flags": [fallback_reason] if fallback_reason else [],
            "parse_status": "not_called",
            "parse_error_type": "",
            "redacted_raw_response_preview": "",
        }

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        clean = str(text or "").strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return clean.strip()

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        s = str(text or "")
        start = s.find("{")
        if start < 0:
            return ""
        depth = 0
        in_str = False
        escaped = False
        for idx in range(start, len(s)):
            ch = s[idx]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : idx + 1]
        return ""

    @staticmethod
    def _extract_json_object_candidates(text: str) -> List[str]:
        s = str(text or "")
        candidates: List[str] = []
        i = 0
        while i < len(s):
            start = s.find("{", i)
            if start < 0:
                break
            depth = 0
            in_str = False
            escaped = False
            end = -1
            for idx in range(start, len(s)):
                ch = s[idx]
                if in_str:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = idx + 1
                        break
            if end > 0:
                candidates.append(s[start:end])
                i = end
            else:
                break
        return candidates

    @staticmethod
    def _is_min_schema_valid(parsed: Dict[str, Any]) -> bool:
        if not isinstance(parsed, dict):
            return False
        if "event_type" not in parsed:
            return False
        if "recommended_stocks" in parsed and not isinstance(parsed.get("recommended_stocks"), list):
            return False
        return True

    @staticmethod
    def _redact_raw_response_preview(raw: str, max_len: int = 2000) -> str:
        text = str(raw or "")
        replace_patterns = [
            r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,;]+)",
            r"(?i)(token\s*[:=]\s*)([^\s,;]+)",
            r"(?i)(secret\s*[:=]\s*)([^\s,;]+)",
            r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)",
        ]
        for pat in replace_patterns:
            text = re.sub(pat, r"\1<REDACTED>", text)
        text = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._\-]+", "Bearer <REDACTED>", text)
        text = re.sub(r"/Users/[^\s\"']+", "<LOCAL_PATH>", text)
        text = re.sub(r"/private/tmp/[^\s\"']+", "<TMP_PATH>", text)
        text = re.sub(r"(?is)Traceback \(most recent call last\):.*", "<REDACTED_TRACEBACK>", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_len:
            text = text[:max_len]
        return text

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
            "fallback_detail": str(payload.get("fallback_detail", "") or ""),
            "a0_event_strength": self._clamp_int(payload.get("a0_event_strength", confidence), 0, 100, confidence),
            "expectation_gap": self._clamp_int(payload.get("expectation_gap", 0), -100, 100, 0),
            "event_state": self._normalize_event_state(payload.get("event_state") or payload.get("narrative_stage"), ""),
            "transmission_candidates": payload.get("transmission_candidates", []),
            "transmission_path": payload.get("transmission_path", []),
            "entities": payload.get("entities", []),
            "narrative_vs_fact": self._normalize_narrative_vs_fact(payload.get("narrative_vs_fact")),
            "event_scope": self._normalize_event_scope(payload.get("event_scope")),
            "novelty_score": self._normalize_novelty_score(payload.get("novelty_score", 0.0)),
            "evidence_spans": payload.get("evidence_spans", []),
            "risk_flags": payload.get("risk_flags", []),
            "parse_status": str(payload.get("parse_status", "") or ""),
            "parse_error_type": str(payload.get("parse_error_type", "") or ""),
            "redacted_raw_response_preview": str(payload.get("redacted_raw_response_preview", "") or ""),
        }
        if not isinstance(output["transmission_candidates"], list):
            output["transmission_candidates"] = []
        output["transmission_candidates"] = [str(x) for x in output["transmission_candidates"] if str(x).strip()][:3]
        if not isinstance(output["transmission_path"], list):
            output["transmission_path"] = []
        output["transmission_path"] = [str(x) for x in output["transmission_path"] if str(x).strip()][:5]
        output["entities"] = self._normalize_entities(output["entities"])
        if not isinstance(output["evidence_spans"], list):
            output["evidence_spans"] = []
        output["evidence_spans"] = [str(x) for x in output["evidence_spans"] if str(x).strip()][:3]
        if not isinstance(output["risk_flags"], list):
            output["risk_flags"] = []
        output["risk_flags"] = [str(x) for x in output["risk_flags"] if str(x).strip()]
        if output["parse_error_type"] and output["parse_error_type"] not in self.PARSE_ERROR_TYPES:
            output["parse_error_type"] = "schema_failed"
        if output["parse_status"] not in {"parse_success", "parse_failed", "not_called"}:
            output["parse_status"] = "parse_failed" if output["parse_error_type"] else "not_called"
        if output["parse_status"] == "parse_success":
            output["parse_error_type"] = ""
            output["redacted_raw_response_preview"] = ""
        if output["parse_status"] == "parse_failed" and not output["parse_error_type"]:
            output["parse_error_type"] = "schema_failed"
        return output

    @classmethod
    def _normalize_event_type(cls, raw_type: Any) -> str:
        event_type = str(raw_type or "").strip().lower()
        return event_type if event_type in cls.ALLOWED_EVENT_TYPES else "other"

    @staticmethod
    def _normalize_narrative_vs_fact(raw: Any) -> str:
        value = str(raw or "").strip().lower()
        if value in {"narrative", "fact", "mixed"}:
            return value
        return "mixed"

    @staticmethod
    def _normalize_event_scope(raw: Any) -> str:
        value = str(raw or "").strip().lower()
        mapping = {
            "macro": "Macro",
            "sector": "Sector",
            "theme": "Theme",
            "sector_theme": "Theme",
        }
        return mapping.get(value, "Sector")

    @staticmethod
    def _normalize_novelty_score(raw: Any) -> float:
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return 0.0
        # Accept both 0..1 and 0..100 user inputs.
        if val > 1.0:
            val = val / 100.0
        return max(0.0, min(1.0, val))

    @staticmethod
    def _normalize_entities(raw: Any) -> List[Dict[str, str]]:
        if not isinstance(raw, list):
            return []
        out: List[Dict[str, str]] = []
        for item in raw:
            if isinstance(item, dict):
                typ = str(item.get("type", "generic") or "generic").strip().lower()
                val = str(item.get("value", "") or "").strip()
                if val:
                    out.append({"type": typ, "value": val})
            else:
                val = str(item or "").strip()
                if val:
                    out.append({"type": "generic", "value": val})
            if len(out) >= 12:
                break
        return out

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

        # Deterministic fallback: keep provider contract explicit even when
        # no provider strategy/keyword branch is matched.
        return {
            "event_type": "other",
            "sentiment": "neutral",
            "confidence": 0,
            "recommended_chain": "",
            "recommended_stocks": [],
            "reason": "deterministic fallback: provider strategy not matched",
            "fallback_reason": "provider_unsupported",
            "provider": provider_lower or "unknown",
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
        not_found_retries: int = 0,
        disable_proxy: bool = False,
    ) -> Tuple[requests.Response | None, str, str]:
        candidates = self._openai_endpoint_candidates()
        if self._openai_endpoint_cache and self._openai_endpoint_cache in candidates:
            candidates = [self._openai_endpoint_cache] + [c for c in candidates if c != self._openai_endpoint_cache]

        last_error = ""
        last_response: requests.Response | None = None
        for endpoint in candidates:
            max_attempts = max(1, int(not_found_retries) + 1)
            for attempt in range(max_attempts):
                try:
                    request_kwargs: Dict[str, Any] = {
                        "headers": headers,
                        "json": payload,
                        "timeout": timeout_seconds,
                    }
                    if disable_proxy:
                        request_kwargs["proxies"] = {"http": "", "https": ""}
                    response = requests.post(endpoint, **request_kwargs)
                except requests.RequestException as exc:
                    last_error = str(exc)
                    if attempt < max_attempts - 1:
                        time.sleep(min(1.2, 0.25 * (attempt + 1)))
                        continue
                    break

                last_response = response
                if response.status_code == 404:
                    last_error = "endpoint_not_found"
                    if attempt < max_attempts - 1:
                        time.sleep(min(0.8, 0.2 * (attempt + 1)))
                        continue
                    break

                self._openai_endpoint_cache = endpoint
                return response, endpoint, ""

        return last_response, "", last_error or "openai_endpoint_not_found"

    def _call_openai_api(self, text: str, timeout_ms: int, *, model: str = "") -> Dict[str, Any]:
        try:
            base_url = self._openai_base_url()
        except RuntimeError as exc:
            return self._abstain_response(
                fallback_reason="openai_base_url_missing",
                fallback_detail=str(exc),
                provider="openai",
                model=model or "unknown",
            )

        prompt = self._get_prompt(text)
        # Normalize Codex model id: "openai-codex/gpt-5.3-codex" -> "gpt-5.3-codex"
        use_model = self._normalize_model_name(model or self.model_name or "gpt-5.3-codex")

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
        if via_gateway:
            # Gateway path can include upstream provider latency; use a wider client timeout window.
            timeout_seconds = max(timeout_seconds, 20.0)
        response, endpoint, route_error = self._post_openai_with_candidates(
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
            not_found_retries=5 if via_gateway else 0,
            disable_proxy=via_gateway,
        )
        if response is None:
            return self._abstain_response(
                fallback_reason="openai_route_error",
                fallback_detail=route_error[:160],
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
                disable_proxy=via_gateway,
            )
            if response is None:
                return self._abstain_response(
                    fallback_reason="openai_route_error",
                    fallback_detail=route_error[:160],
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
                    disable_proxy=via_gateway,
                )
                if response is None:
                    return self._abstain_response(
                        fallback_reason="openai_route_error",
                        fallback_detail=route_error[:160],
                        provider="openai",
                        model=use_model,
                    )

        # Gateway occasionally returns transient 404 on otherwise healthy routes.
        # Re-probe once with cache cleared before finalizing fallback.
        if response.status_code == 404 and via_gateway:
            self._openai_endpoint_cache = ""
            response, endpoint, route_error = self._post_openai_with_candidates(
                headers=headers,
                payload=payload,
                timeout_seconds=timeout_seconds,
                not_found_retries=5,
                disable_proxy=True,
            )
            if response is None:
                return self._abstain_response(
                    fallback_reason="openai_route_error",
                    fallback_detail=route_error[:160],
                    provider="openai",
                    model=use_model,
                )

        if response.status_code >= 400:
            reason = self._extract_openai_error(response)
            return self._abstain_response(
                fallback_reason="openai_http_error",
                fallback_detail=f"status={response.status_code}; {reason[:120]}",
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
  - recommended_chain: string naming the asset-pricing chain (e.g. "tariff_chain", "rate_cut_chain"), empty string if none
  - recommended_stocks: array of ticker symbols, empty array if none
  - event_state: one of [Initial, Developing, Peak, Fading, Dead]
  - narrative_vs_fact: one of [narrative, fact, mixed]
  - event_scope: one of [Macro, Sector, Theme]
  - novelty_score: float between 0 and 1
  - entities: array of objects [{{"type":"...", "value":"..."}}], 0..12 items
  - transmission_path: array of causal steps, 1..5 items
  - transmission_candidates: array of short strings, 0..3 items
  - evidence_spans: array of short source snippets, 1..3 items
  - risk_flags: array of strings
  - reason: short sentence
- If no clear listed ticker appears in the news, return recommended_stocks as [].
- Do NOT invent or hallucinate ticker symbols.

News text:
{text}
"""

    def _parse_ai_content(self, content: str) -> Dict[str, Any]:
        stripped = self._strip_code_fence(content)
        redacted_preview = self._redact_raw_response_preview(stripped)
        if not stripped:
            out = self._abstain_response(fallback_reason="empty_response", provider="ai")
            out["parse_status"] = "parse_failed"
            out["parse_error_type"] = "empty_response"
            out["redacted_raw_response_preview"] = redacted_preview
            return out

        parsed_any: Any = None
        direct_loaded = False
        try:
            parsed_any = json.loads(stripped)
            direct_loaded = True
        except json.JSONDecodeError:
            direct_loaded = False

        if not direct_loaded:
            candidates = self._extract_json_object_candidates(stripped)
            if not candidates:
                parse_error = "truncated_response" if "{" in stripped else "no_json_object"
                out = self._abstain_response(fallback_reason="json_parse_failed", provider="ai")
                out["parse_status"] = "parse_failed"
                out["parse_error_type"] = parse_error
                out["redacted_raw_response_preview"] = redacted_preview
                out["reason"] = parse_error
                return out

            last_json_error = "invalid_json_syntax"
            best_parsed: Any = None
            for candidate in candidates:
                try:
                    candidate_parsed = json.loads(candidate.strip())
                except json.JSONDecodeError:
                    last_json_error = "invalid_json_syntax"
                    continue
                if isinstance(candidate_parsed, dict) and self._is_min_schema_valid(candidate_parsed):
                    best_parsed = candidate_parsed
                    break
                if best_parsed is None:
                    best_parsed = candidate_parsed

            if best_parsed is None:
                out = self._abstain_response(fallback_reason="json_parse_failed", provider="ai")
                out["parse_status"] = "parse_failed"
                out["parse_error_type"] = last_json_error
                out["redacted_raw_response_preview"] = redacted_preview
                out["reason"] = last_json_error
                return out
            parsed_any = best_parsed

        if not isinstance(parsed_any, dict):
            out = self._abstain_response(fallback_reason="json_parse_failed", provider="ai")
            out["parse_status"] = "parse_failed"
            out["parse_error_type"] = "root_not_object"
            out["redacted_raw_response_preview"] = redacted_preview
            out["reason"] = "root_not_object"
            return out

        parsed = parsed_any
        if "recommended_stocks" in parsed and not isinstance(parsed.get("recommended_stocks"), list):
            out = self._abstain_response(fallback_reason="schema_failed", provider="ai")
            out["parse_status"] = "parse_failed"
            out["parse_error_type"] = "recommended_stocks_not_list"
            out["redacted_raw_response_preview"] = redacted_preview
            out["reason"] = "recommended_stocks_not_list"
            return out

        if "event_type" not in parsed:
            out = self._abstain_response(fallback_reason="schema_failed", provider="ai")
            out["parse_status"] = "parse_failed"
            out["parse_error_type"] = "schema_failed"
            out["redacted_raw_response_preview"] = redacted_preview
            out["reason"] = "schema_failed"
            return out

        return {
            "event_type": self._normalize_event_type(parsed.get("event_type", "other")),
            "sentiment": parsed.get("sentiment", "neutral"),
            "confidence": parsed.get("confidence", 50),
            "recommended_chain": parsed.get("recommended_chain", ""),
            "recommended_stocks": parsed.get("recommended_stocks", []),
            "a0_event_strength": parsed.get("a0_event_strength", parsed.get("confidence", 50)),
            "expectation_gap": parsed.get("expectation_gap", 0),
            "event_state": parsed.get("event_state", "Initial"),
            "narrative_vs_fact": parsed.get("narrative_vs_fact", "mixed"),
            "event_scope": parsed.get("event_scope", "Sector"),
            "novelty_score": parsed.get("novelty_score", 0.0),
            "entities": parsed.get("entities", []),
            "transmission_path": parsed.get("transmission_path", []),
            "transmission_candidates": parsed.get("transmission_candidates", []),
            "evidence_spans": parsed.get("evidence_spans", []),
            "risk_flags": parsed.get("risk_flags", []),
            "reason": parsed.get("reason", "success"),
            "parse_status": "parse_success",
            "parse_error_type": "",
            "redacted_raw_response_preview": "",
        }

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
                parsed = self._parse_ai_content(str(content or ""))
                parsed["provider"] = self._provider_name()
                parsed["model"] = model or self.model_name
                if not parsed.get("reason"):
                    parsed["reason"] = f"{self.model_name} api response"
                return parsed

            out = self._abstain_response(
                fallback_reason="empty_response",
                provider=self._provider_name(),
                model=model or self.model_name,
            )
            out["parse_status"] = "parse_failed"
            out["parse_error_type"] = "empty_response"
            out["reason"] = f"{self.model_name} no choices returned"
            return out

        except requests.exceptions.Timeout:
            out = self._abstain_response(
                fallback_reason="timeout",
                provider=self._provider_name(),
                model=model or self.model_name,
            )
            out["parse_status"] = "not_called"
            out["parse_error_type"] = "timeout"
            out["reason"] = f"{self.model_name} timeout"
            return out
        except requests.exceptions.RequestException as e:
            out = self._abstain_response(
                fallback_reason="provider_error",
                fallback_detail=f"{self.model_name} API error: {str(e)[:100]}",
                provider=self._provider_name(),
                model=model or self.model_name,
            )
            out["parse_status"] = "not_called"
            out["parse_error_type"] = "provider_error"
            return out
        except Exception as e:
            out = self._abstain_response(
                fallback_reason="provider_error",
                fallback_detail=f"{self.model_name} error: {str(e)[:100]}",
                provider=self._provider_name(),
                model=model or self.model_name,
            )
            out["parse_status"] = "not_called"
            out["parse_error_type"] = "provider_error"
            return out

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
            out["parse_status"] = "not_called"
            out["parse_error_type"] = "timeout"
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
            out["parse_status"] = "not_called"
            out["parse_error_type"] = "provider_error"
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
            if not out.get("parse_status"):
                out["parse_status"] = "parse_success"
            return out

        if out["recommended_chain"] or out.get("transmission_candidates"):
            out["verdict"] = "hit"
            out["semantic_status"] = "hit"
            if not out["reason"]:
                out["reason"] = "semantic hit"
            if not out.get("fallback_reason"):
                out["fallback_reason"] = ""
            out.update(self.analyze_event(headline, raw_text, semantic_output=out))
            if not out.get("parse_status"):
                out["parse_status"] = "parse_success"
            return out

        out["verdict"] = "abstain"
        out["semantic_status"] = "fallback"
        if not out.get("fallback_reason"):
            out["fallback_reason"] = "chain_missing"
        if not out["reason"]:
            out["reason"] = "missing recommended chain"
        out.update(self.analyze_event(headline, raw_text, semantic_output=out))
        if not out.get("parse_status"):
            out["parse_status"] = "parse_success"
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
        normalized_entities = self._normalize_entities(semantic.get("entities", []))
        transmission_path = semantic.get("transmission_path", [])
        if not isinstance(transmission_path, list):
            transmission_path = []
        normalized_path = [str(x) for x in transmission_path if str(x).strip()][:5]

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
            "narrative_vs_fact": self._normalize_narrative_vs_fact(semantic.get("narrative_vs_fact")),
            "event_scope": self._normalize_event_scope(semantic.get("event_scope")),
            "novelty_score": self._normalize_novelty_score(semantic.get("novelty_score", 0.0)),
            "entities": normalized_entities,
            "transmission_path": normalized_path,
            "transmission_candidates": normalized_candidates or self._transmission_candidates(event_type, sentiment)[:3],
            "evidence_grade": evidence_grade,
            "evidence_spans": self._evidence_spans(headline, raw_text),
            "risk_flags": risk_flags,
        }
