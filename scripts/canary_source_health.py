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
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

try:
    from ai_event_intel import NewsIngestion
except Exception:  # noqa: BLE001
    NewsIngestion = None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_CANARY_SOURCE_ID = "reuters_rss_top_news"
DEFAULT_CANARY_SOURCE_URL = "https://feeds.reuters.com/reuters/topNews"
DEFAULT_CANARY_SOURCE_KIND = "rss"


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
        return None
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        self.audit_dir = Path(audit_dir) if audit_dir else _default_log_dir()
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.health_log_file = self.audit_dir / "canary_health.jsonl"
        self.health_summary_file = self.audit_dir / "canary_health_summary.json"
        self.health_report_file = self.audit_dir / "canary_health_report.json"
        self.config = self._load_config()
        self.settings = self._load_settings()
        self.source_id = str(self.settings.get("source_id", DEFAULT_CANARY_SOURCE_ID))
        self.source_url = str(self.settings.get("source_url", DEFAULT_CANARY_SOURCE_URL))
        self.source_kind = str(self.settings.get("source_kind", DEFAULT_CANARY_SOURCE_KIND))
        self.timeout = int(self.settings.get("timeout", 10))
        self.max_items = int(self.settings.get("max_items", 10))
        self.window_minutes = self._window_minutes()
        gate = self.settings.get("gate", {}) or {}
        self.min_success_rate_1h = float(gate.get("min_success_rate_1h", 0.95))
        self.max_p95_latency_ms = float(gate.get("max_p95_latency_ms", 3000))
        self.max_freshness_lag_sec = float(gate.get("max_freshness_lag_sec", 1800))
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

    def _collect_feed_items(self, source_url: str, timeout: int, max_items: int) -> tuple[str, List[Dict[str, Any]], Optional[str]]:
        if NewsIngestion is None:
            return "failed", [], "NewsIngestion unavailable"
        try:
            out = NewsIngestion(str(self.config_path)).run({
                "sources": [source_url],
                "max_items": max_items,
                "timeout": timeout,
                "retries": 0,
            })
        except Exception as exc:  # noqa: BLE001
            return "failed", [], str(exc)

        items = out.data.get("items", []) if isinstance(out.data, dict) else []
        if not isinstance(items, list):
            return "failed", [], "invalid items payload"

        real_items = [
            item for item in items
            if isinstance(item, dict)
            and not bool(item.get("is_test_data"))
            and str(item.get("source_type", "")).lower() != "fallback"
        ]
        if not real_items:
            return "failed", [], "fallback_or_test_data"
        return "success", real_items, None

    def collect_once(self) -> Dict[str, Any]:
        fetched_at = _now_iso()
        attempt_id = f"CANARY-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        started = time.perf_counter()
        status, items, error = self._collect_feed_items(self.source_url, self.timeout, self.max_items)
        fetch_latency_ms = round((time.perf_counter() - started) * 1000.0, 2)

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
            "source_url": self.source_url,
            "source_kind": self.source_kind,
            "trace_id": attempt_id,
            "fetched_at": fetched_at,
            "published_at": max(published_times).isoformat().replace("+00:00", "Z") if published_times else None,
            "is_canary": True,
            "fetch_status": status,
            "fetch_latency_ms": fetch_latency_ms,
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
