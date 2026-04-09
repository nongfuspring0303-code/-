#!/usr/bin/env python3
"""
Canary source health collector and rolling statistics.

The default canary source is Reuters Top News RSS. This module stores
append-only fetch attempts and derives rolling health windows that can be
consumed by health checks and release gates.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET
import urllib.error
import urllib.request

try:
    import yaml
except ImportError:
    yaml = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_CANARY_SOURCE_ID = "reuters_rss_top_news"
DEFAULT_CANARY_SOURCE_URL = "https://feeds.reuters.com/reuters/topNews"
DEFAULT_CANARY_SOURCE_KIND = "rss"
DEFAULT_CANARY_SOURCE_URLS = [
    DEFAULT_CANARY_SOURCE_URL,
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "https://www.reuters.com/markets/rss",
    "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&hl=en-US&gl=US&ceid=US:en",
]
DEFAULT_RETRY_DELAYS_SEC = [5, 10, 20]


def _root_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_log_dir() -> Path:
    return _root_dir() / "logs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, IndexError):
            return None
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _find_atom_link(entry: ET.Element, namespace: str) -> str:
    for link in entry.findall(f"{namespace}link"):
        href = (link.attrib.get("href") or "").strip()
        rel = (link.attrib.get("rel") or "alternate").strip().lower()
        if href and rel in {"alternate", "self", ""}:
            return href
    return ""


def _parse_atom(xml_text: str, source_url: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    namespace = ""
    if root.tag.startswith("{") and "}" in root.tag:
        namespace = root.tag.split("}", 1)[0] + "}"
    items: List[Dict[str, Any]] = []
    entries = root.findall(f".//{namespace}entry") or root.findall(".//entry")
    for entry in entries:
        title = (entry.findtext(f"{namespace}title") or entry.findtext("title") or "").strip()
        if not title:
            continue
        link = _find_atom_link(entry, namespace) or source_url
        updated = (entry.findtext(f"{namespace}updated") or entry.findtext("updated") or "").strip()
        published = (entry.findtext(f"{namespace}published") or entry.findtext("published") or "").strip()
        timestamp = updated or published
        summary = (entry.findtext(f"{namespace}summary") or entry.findtext("summary") or entry.findtext(f"{namespace}content") or entry.findtext("content") or "").strip()
        items.append(
            {
                "headline": title,
                "source_url": link,
                "timestamp": timestamp,
                "raw_text": summary,
                "source_type": "atom",
            }
        )
    return items


def _parse_rss(xml_text: str, source_url: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: List[Dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        link = (item.findtext("link") or source_url).strip() or source_url
        pub_date = (item.findtext("pubDate") or item.findtext("date") or item.findtext("published") or "").strip()
        description = (item.findtext("description") or item.findtext("summary") or "").strip()
        items.append(
            {
                "headline": title,
                "source_url": link,
                "timestamp": pub_date,
                "raw_text": description,
                "source_type": "rss",
            }
        )
    return items


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    index = max(0, min(len(ordered) - 1, index))
    return float(ordered[index])


@dataclass
class CanaryAssessment:
    status: str
    summary: str
    warnings: List[str]
    errors: List[str]
    evidence: List[str]
    windows: Dict[str, Dict[str, Any]]


class CanarySourceHealth:
    def __init__(self, config_path: Optional[str] = None, audit_dir: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else _root_dir() / "configs" / "edt-modules-config.yaml"
        self.config = self._load_config()
        self.settings = self._load_settings()
        configured_audit_dir = self.settings.get("audit_dir")
        if audit_dir:
            self.audit_dir = Path(audit_dir)
        elif configured_audit_dir:
            configured_path = Path(str(configured_audit_dir))
            self.audit_dir = configured_path if configured_path.is_absolute() else _root_dir() / configured_path
        else:
            self.audit_dir = _default_log_dir()
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.health_log_file = self.audit_dir / "canary_health.jsonl"
        self.health_summary_file = self.audit_dir / "canary_health_summary.json"
        self.health_report_file = self.audit_dir / "canary_health_report.json"
        self.source_id = str(self.settings.get("source_id", DEFAULT_CANARY_SOURCE_ID))
        self.source_url = str(self.settings.get("source_url", DEFAULT_CANARY_SOURCE_URL))
        self.source_kind = str(self.settings.get("source_kind", DEFAULT_CANARY_SOURCE_KIND))
        self.sources = self._source_candidates()
        self.timeout = int(self.settings.get("timeout", 10))
        self.max_items = int(self.settings.get("max_items", 10))
        self.window_minutes = self._window_minutes()
        self.retry_delays_sec = self._retry_delays()
        gate = self._effective_gate_settings()
        self.min_success_rate_1h = float(gate.get("min_success_rate_1h", 0.95))
        self.max_p95_latency_ms = float(gate.get("max_p95_latency_ms", 3000))
        self.max_freshness_lag_sec = float(gate.get("max_freshness_lag_sec", 21600))
        self.min_new_item_count_30m = int(gate.get("min_new_item_count_30m", 1))

    def _load_config(self) -> Dict[str, Any]:
        if not yaml or not self.config_path.exists():
            return {}
        try:
            return yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    def _get_config(self, path: str, default: Any = None) -> Any:
        value: Any = self.config
        for key in path.split("."):
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        return value

    def _load_settings(self) -> Dict[str, Any]:
        runtime_settings = self._get_config("runtime.canary_source_health", {})
        if isinstance(runtime_settings, dict) and runtime_settings:
            return runtime_settings
        top_level = self._get_config("canary_source_health", {})
        return top_level if isinstance(top_level, dict) else {}

    def _window_minutes(self) -> List[int]:
        raw = self.settings.get("windows_minutes", [5, 60, 30])
        if isinstance(raw, list) and raw:
            values = []
            for item in raw:
                try:
                    values.append(int(item))
                except (TypeError, ValueError):
                    continue
            return values or [5, 60, 30]
        return [5, 60, 30]

    def _source_candidates(self) -> List[Dict[str, Any]]:
        raw_sources = self.settings.get("sources", [])
        values: List[Dict[str, Any]] = []
        if isinstance(raw_sources, list):
            for item in raw_sources:
                if isinstance(item, str) and item.strip():
                    values.append({"url": item.strip(), "kind": self.source_kind})
                elif isinstance(item, dict):
                    url = str(item.get("url", "")).strip()
                    if not url:
                        continue
                    values.append({
                        "url": url,
                        "kind": str(item.get("kind", self.source_kind)),
                        "api_key_env": str(item.get("api_key_env", "") or ""),
                        "headers": item.get("headers", {}) if isinstance(item.get("headers", {}), dict) else {},
                    })
        if not values:
            values = [{"url": self.source_url, "kind": self.source_kind}]
        if self.source_url not in [spec["url"] for spec in values]:
            values.insert(0, {"url": self.source_url, "kind": self.source_kind})
        return values

    def _retry_delays(self) -> List[int]:
        raw = self.settings.get("retry_delays_sec", DEFAULT_RETRY_DELAYS_SEC)
        values: List[int] = []
        if isinstance(raw, list):
            for item in raw:
                try:
                    delay = int(item)
                except (TypeError, ValueError):
                    continue
                if delay > 0:
                    values.append(delay)
        return values or list(DEFAULT_RETRY_DELAYS_SEC)

    def _effective_gate_settings(self) -> Dict[str, Any]:
        gate = self.settings.get("gate", {}) or {}
        if not isinstance(gate, dict):
            return {}
        overrides = gate.get("source_overrides", {}) or {}
        if isinstance(overrides, dict):
            source_override = overrides.get(self.source_id, {})
            if isinstance(source_override, dict) and source_override:
                merged = dict(gate)
                merged.update(source_override)
                return merged
        return gate

    def _load_records(self, window_minutes: int = 60) -> List[Dict[str, Any]]:
        if not self.health_log_file.exists():
            return []
        cutoff = datetime.now(timezone.utc).timestamp() - (max(1, window_minutes) * 60)
        rows: List[Dict[str, Any]] = []
        with open(self.health_log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fetched_at = _parse_ts(row.get("fetched_at"))
                if not fetched_at:
                    continue
                if fetched_at.timestamp() >= cutoff:
                    rows.append(row)
        return rows

    def _attempt_metrics(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_attempts = len(records)
        success_records = [row for row in records if row.get("fetch_status") == "success"]
        success_count = len(success_records)
        latencies = [float(row.get("fetch_latency_ms", 0.0) or 0.0) for row in records]
        freshness_values = [
            float(row.get("freshness_lag_sec", 0.0) or 0.0)
            for row in success_records
            if row.get("freshness_lag_sec") is not None
        ]
        new_item_count = sum(int(row.get("new_item_count", 0) or 0) for row in success_records)
        live_sample_count = sum(1 for row in success_records if int(row.get("new_item_count", 0) or 0) > 0)

        return {
            "window_minutes": 0,
            "total_attempts": total_attempts,
            "success_count": success_count,
            "success_rate": round(success_count / total_attempts, 4) if total_attempts else 0.0,
            "p95_latency_ms": round(_percentile(latencies, 95), 2),
            "freshness_lag_sec": round(_percentile(freshness_values, 95), 2),
            "new_item_count": new_item_count,
            "live_sample_count": live_sample_count,
            "last_record": records[-1] if records else {},
        }

    def _parse_feed_items(self, xml_text: str, source_url: str) -> List[Dict[str, Any]]:
        root = ET.fromstring(xml_text)
        if root.tag.endswith("feed"):
            items = _parse_atom(xml_text, source_url)
        else:
            items = _parse_rss(xml_text, source_url)
        return [
            item
            for item in items
            if isinstance(item, dict) and item.get("headline") and not bool(item.get("is_test_data"))
        ]

    def _resolve_headers(self, source_spec: Dict[str, Any]) -> Dict[str, str]:
        headers = {
            "User-Agent": "EDT-Canary/1.0 Mozilla/5.0",
            "Accept": "application/rss+xml, application/xml;q=0.9, application/json;q=0.8, */*;q=0.7",
        }
        custom_headers = source_spec.get("headers", {})
        if isinstance(custom_headers, dict):
            for key, value in custom_headers.items():
                if key and value is not None:
                    headers[str(key)] = str(value)
        api_key_env = str(source_spec.get("api_key_env", "") or "")
        if api_key_env:
            api_key = os.getenv(api_key_env, "").strip()
            if api_key:
                headers.setdefault("X-Api-Key", api_key)
        return headers

    def _fetch_source_once(self, source_spec: Dict[str, Any], timeout: int, max_items: int) -> Dict[str, Any]:
        source_url = str(source_spec.get("url", self.source_url))
        source_kind = str(source_spec.get("kind", self.source_kind)).lower()
        started = time.perf_counter()
        headers = self._resolve_headers(source_spec)
        try:
            req = urllib.request.Request(source_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "items": [],
                "error": f"fetch_failed:{exc}",
                "fetch_latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
            }

        try:
            if source_kind in {"json", "newsapi"} or "newsapi.org" in source_url:
                items = self._parse_newsapi_items(payload, source_url)
            else:
                items = self._parse_feed_items(payload, source_url)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "items": [],
                "error": f"parse_failed:{exc}",
                "fetch_latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
            }
        if not items:
            return {
                "status": "failed",
                "items": [],
                "error": "empty_or_test_data",
                "fetch_latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
            }
        return {
            "status": "success",
            "items": items[:max_items],
            "error": None,
            "fetch_latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
        }

    def _parse_newsapi_items(self, json_text: str, source_url: str) -> List[Dict[str, Any]]:
        payload = json.loads(json_text)
        if str(payload.get("status", "")).lower() != "ok":
            return []
        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            return []
        items: List[Dict[str, Any]] = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            title = (article.get("title") or "").strip()
            if not title:
                continue
            published_at = article.get("publishedAt") or article.get("published_at")
            source_name = ""
            source = article.get("source")
            if isinstance(source, dict):
                source_name = str(source.get("name", "") or "").strip()
            items.append(
                {
                    "headline": title,
                    "source_url": article.get("url", source_url),
                    "timestamp": published_at,
                    "raw_text": (article.get("description") or article.get("content") or "").strip(),
                    "source_type": "newsapi",
                    "source_name": source_name,
                }
            )
        return items

    def _collect_feed_items(
        self,
        source_specs: Sequence[Dict[str, Any]],
        timeout: int,
        max_items: int,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
        attempted_sources: List[Dict[str, Any]] = []
        last_latency_ms = 0.0
        for source_spec in source_specs:
            source_url = str(source_spec.get("url", self.source_url))
            source_attempts: List[Dict[str, Any]] = []
            delays = [0] + self.retry_delays_sec
            for attempt_index, delay in enumerate(delays):
                if delay > 0:
                    time.sleep(delay)
                result = self._fetch_source_once(source_spec, timeout, max_items)
                last_latency_ms = float(result.get("fetch_latency_ms", 0.0) or 0.0)
                source_attempts.append(
                    {
                        "attempt": attempt_index + 1,
                        "status": result["status"],
                        "error": result["error"],
                        "fetch_latency_ms": result["fetch_latency_ms"],
                    }
                )
                if result["status"] == "success":
                    attempted_sources.append(
                        {
                            "source_url": source_url,
                            "source_kind": source_spec.get("kind", self.source_kind),
                            "status": "success",
                            "attempts": source_attempts,
                        }
                    )
                    return "success", result["items"], None, {
                        "attempted_sources": attempted_sources,
                        "used_source_url": source_url,
                        "fetch_latency_ms": last_latency_ms,
                        "source_attempts": source_attempts,
                    }
            attempted_sources.append(
                {
                    "source_url": source_url,
                    "source_kind": source_spec.get("kind", self.source_kind),
                    "status": "failed",
                    "attempts": source_attempts,
                }
            )

        last_error = attempted_sources[-1]["attempts"][-1]["error"] if attempted_sources else "no_sources"
        return "failed", [], last_error, {
            "attempted_sources": attempted_sources,
            "used_source_url": None,
            "fetch_latency_ms": last_latency_ms,
            "source_attempts": attempted_sources[-1]["attempts"] if attempted_sources else [],
        }

    def collect_once(self) -> Dict[str, Any]:
        fetched_at = _now_iso()
        attempt_id = f"CANARY-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        started = time.perf_counter()
        status, items, error, attempt_meta = self._collect_feed_items(self.sources, self.timeout, self.max_items)
        total_elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        fetch_latency_ms = float(attempt_meta.get("fetch_latency_ms", total_elapsed_ms) or total_elapsed_ms)

        parsed_items: List[Dict[str, Any]] = []
        published_times: List[datetime] = []
        freshness_values: List[float] = []
        for idx, item in enumerate(items):
            published_at = item.get("timestamp") or item.get("published_at")
            parsed = _parse_ts(published_at)
            if parsed:
                published_times.append(parsed)
                freshness_values.append(max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds()))
            item_trace = f"{attempt_id}-{idx + 1}"
            parsed_items.append(
                {
                    "source_id": self.source_id,
                    "source_url": item.get("source_url", self.source_url),
                    "headline": item.get("headline", ""),
                    "published_at": parsed.isoformat().replace("+00:00", "Z") if parsed else None,
                    "trace_id": item_trace,
                    "is_canary": True,
                    "source_kind": str(item.get("source_type", self.source_kind)),
                }
            )

        record = {
            "record_type": "canary_fetch",
            "source_id": self.source_id,
            "source_url": attempt_meta.get("used_source_url") or self.source_url,
            "primary_source_url": self.source_url,
            "source_kind": self.source_kind,
            "trace_id": attempt_id,
            "fetched_at": fetched_at,
            "published_at": max(published_times).isoformat().replace("+00:00", "Z") if published_times else None,
            "is_canary": True,
            "fetch_status": status,
            "fetch_latency_ms": fetch_latency_ms,
            "total_elapsed_ms": total_elapsed_ms,
            "retry_delays_sec": list(self.retry_delays_sec),
            "attempted_sources": attempt_meta.get("attempted_sources", []),
            "freshness_lag_sec": round(max(freshness_values), 2) if freshness_values else None,
            "new_item_count": len(parsed_items),
            "items": parsed_items,
        }
        if status != "success":
            record["error"] = error or "unknown"

        with open(self.health_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.write_summary()
        return record

    def summarize(self, window_minutes: int = 60) -> Dict[str, Any]:
        records = self._load_records(window_minutes=window_minutes)
        metrics = self._attempt_metrics(records)
        metrics["window_minutes"] = window_minutes
        return metrics

    def build_summary(self) -> Dict[str, Any]:
        windows = {str(window): self.summarize(window) for window in self.window_minutes}
        recent_30m = self.summarize(30)
        last_record = recent_30m.get("last_record", {}) if recent_30m else {}
        summary = {
            "schema_version": "v1.0",
            "generated_at": _now_iso(),
            "source_id": self.source_id,
            "source_url": self.source_url,
            "source_kind": self.source_kind,
            "windows": windows,
            "recent_30m": recent_30m,
            "last_record": last_record,
        }
        return summary

    def write_summary(self) -> Dict[str, Any]:
        summary = self.build_summary()
        with open(self.health_summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        self.write_report(summary=summary)
        return summary

    def read_summary(self) -> Dict[str, Any]:
        if not self.health_summary_file.exists():
            return self.write_summary()
        try:
            return json.loads(self.health_summary_file.read_text(encoding="utf-8"))
        except Exception:
            return self.write_summary()

    def build_report(self, summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        summary = summary or self.read_summary()
        return {
            "schema_version": "v1.0",
            "generated_at": _now_iso(),
            "source_id": summary.get("source_id", self.source_id),
            "source_url": summary.get("source_url", self.source_url),
            "source_kind": summary.get("source_kind", self.source_kind),
            "windows": {
                "5m": summary.get("windows", {}).get("5", {}),
                "30m": summary.get("recent_30m", {}),
                "1h": summary.get("windows", {}).get("60", {}),
            },
            "last_record": summary.get("last_record", {}),
        }

    def write_report(self, summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        report = self.build_report(summary=summary)
        with open(self.health_report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return report

    def assess(self, summary: Optional[Dict[str, Any]] = None, *, mode: str = "dev") -> CanaryAssessment:
        summary = summary or self.read_summary()
        window_1h = summary.get("windows", {}).get("60", {})
        window_30m = summary.get("recent_30m", {})
        total_attempts = int(window_1h.get("total_attempts", 0) or 0)
        success_count = int(window_1h.get("success_count", 0) or 0)
        live_sample_count = int(window_1h.get("live_sample_count", 0) or 0)
        success_rate = float(window_1h.get("success_rate", 0.0) or 0.0)
        p95_latency_ms = float(window_1h.get("p95_latency_ms", 0.0) or 0.0)
        freshness_lag_sec = float(window_1h.get("freshness_lag_sec", 0.0) or 0.0)
        new_item_count_30m = int(window_30m.get("new_item_count", 0) or 0)

        warnings: List[str] = []
        errors: List[str] = []
        evidence = [
            f"source_id={summary.get('source_id', self.source_id)}",
            f"source_url={summary.get('source_url', self.source_url)}",
            f"total_attempts_1h={total_attempts}",
            f"success_count_1h={success_count}",
            f"live_sample_count_1h={live_sample_count}",
            f"success_rate_1h={success_rate}",
            f"p95_latency_ms_1h={p95_latency_ms}",
            f"freshness_lag_sec_1h={freshness_lag_sec}",
            f"new_item_count_30m={new_item_count_30m}",
        ]

        if total_attempts <= 0 or live_sample_count <= 0:
            return CanaryAssessment(
                status="YELLOW",
                summary="No live canary samples recorded yet.",
                warnings=["Canary evidence is still replay-only or unavailable."],
                errors=[],
                evidence=evidence,
                windows=summary.get("windows", {}),
            )

        if success_rate < self.min_success_rate_1h:
            errors.append(f"success_rate_1h={success_rate} < {self.min_success_rate_1h}")
        if p95_latency_ms > self.max_p95_latency_ms:
            errors.append(f"p95_latency_ms_1h={p95_latency_ms} > {self.max_p95_latency_ms}")
        if freshness_lag_sec > self.max_freshness_lag_sec:
            errors.append(f"freshness_lag_sec_1h={freshness_lag_sec} > {self.max_freshness_lag_sec}")
        if new_item_count_30m < self.min_new_item_count_30m:
            errors.append(f"new_item_count_30m={new_item_count_30m} < {self.min_new_item_count_30m}")

        if errors:
            return CanaryAssessment(
                status="RED",
                summary="Canary source health is below threshold.",
                warnings=warnings,
                errors=errors,
                evidence=evidence,
                windows=summary.get("windows", {}),
            )

        return CanaryAssessment(
            status="GREEN",
            summary="Canary source health is within threshold.",
            warnings=warnings,
            errors=errors,
            evidence=evidence,
            windows=summary.get("windows", {}),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and summarize Reuters canary source health.")
    parser.add_argument("--refresh", action="store_true", help="Fetch one canary sample before summarizing.")
    parser.add_argument("--audit-dir", type=str, default=None, help="Audit directory for canary logs.")
    parser.add_argument("--config", type=str, default=None, help="Config path override.")
    args = parser.parse_args()

    health = CanarySourceHealth(config_path=args.config, audit_dir=args.audit_dir)
    if args.refresh:
        record = health.collect_once()
        print(json.dumps(record, ensure_ascii=False, indent=2))
    summary = health.read_summary()
    report = health.write_report(summary=summary)
    assessment = health.assess(summary=summary)
    print(json.dumps({
        "assessment": {
            "status": assessment.status,
            "summary": assessment.summary,
            "warnings": assessment.warnings,
            "errors": assessment.errors,
            "evidence": assessment.evidence,
            "windows": assessment.windows,
        },
        "report": report,
    }, ensure_ascii=False, indent=2))
    return 0 if assessment.status == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
