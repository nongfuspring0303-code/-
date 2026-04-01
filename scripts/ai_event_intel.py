#!/usr/bin/env python3
"""
AI event intelligence modules for A-layer.
- NewsIngestion (A0)
- EventEvidenceScorer (A1)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import time
import uuid
import xml.etree.ElementTree as ET
import urllib.request
from email.utils import parsedate_to_datetime

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus
from pathlib import Path


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_trace_id() -> str:
    return f"TRC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def _parse_datetime(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        try:
            return parsedate_to_datetime(ts)
        except Exception:
            return None


def _normalize_timestamp(ts: Optional[str]) -> str:
    dt = _parse_datetime(ts)
    if not dt:
        return _now_iso()
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_rss(xml_text: str, source_url: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or source_url).strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        if not title:
            continue
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


def _safe_fetch(url: str, timeout: int) -> Optional[str]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _dedupe_items(items: List[Dict[str, Any]], window_minutes: int) -> List[Dict[str, Any]]:
    seen: Dict[str, datetime] = {}
    output: List[Dict[str, Any]] = []
    window_seconds = max(1, window_minutes) * 60

    for item in items:
        headline = (item.get("headline") or "").strip().lower()
        host = urlparse(item.get("source_url", "")).netloc.lower().replace("www.", "")
        key = f"{headline}|{host}"
        dt = _parse_datetime(item.get("timestamp"))
        if key in seen and dt and (dt - seen[key]).total_seconds() <= window_seconds:
            continue
        if key not in seen and dt:
            seen[key] = dt
        output.append(item)
    return output


class NewsIngestion(EDTModule):
    """A0: real news ingestion with fallback and standardization."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("NewsIngestion", "1.0.0", config_path or _default_config_path())

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        items_override = raw.get("items_override")
        max_items = int(raw.get("max_items", 10))

        if items_override:
            normalized = [self._normalize_item(item) for item in items_override]
            dedupe_on = bool(self._get_config("modules.NewsIngestion.params.dedupe", True))
            window_minutes = int(self._get_config("modules.NewsIngestion.params.dedupe_window_minutes", 120))
            if dedupe_on:
                normalized = _dedupe_items(normalized, window_minutes)
            return ModuleOutput(status=ModuleStatus.SUCCESS, data={"items": normalized[:max_items]})

        sources = raw.get("sources") or self._get_config("modules.NewsIngestion.params.sources", [])
        timeout = int(self._get_config("modules.NewsIngestion.params.timeout", 8))
        retries = int(self._get_config("modules.NewsIngestion.params.retries", 2))

        items: List[Dict[str, Any]] = []
        for src in sources:
            xml_text = None
            for _ in range(retries + 1):
                xml_text = _safe_fetch(src, timeout)
                if xml_text:
                    break
                time.sleep(0.5)
            if not xml_text:
                continue
            try:
                items.extend(_parse_rss(xml_text, src))
            except Exception:
                continue

        if not items:
            items = [
                {
                    "headline": "Fed announces emergency liquidity action",
                    "source_url": "https://www.federalreserve.gov/",
                    "timestamp": _now_iso(),
                    "raw_text": "Fallback news item used when sources fail.",
                    "source_type": "official",
                }
            ]

        normalized = [self._normalize_item(item) for item in items]
        dedupe_on = bool(self._get_config("modules.NewsIngestion.params.dedupe", True))
        window_minutes = int(self._get_config("modules.NewsIngestion.params.dedupe_window_minutes", 120))
        if dedupe_on:
            normalized = _dedupe_items(normalized, window_minutes)
        return ModuleOutput(status=ModuleStatus.SUCCESS, data={"items": normalized[:max_items]})

    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = item.get("trace_id") or _new_trace_id()
        timestamp = _normalize_timestamp(item.get("timestamp"))
        return {
            "trace_id": trace_id,
            "event_id": item.get("event_id", ""),
            "headline": item.get("headline", ""),
            "source_url": item.get("source_url", ""),
            "timestamp": timestamp,
            "raw_text": item.get("raw_text", ""),
            "source_type": item.get("source_type", ""),
            "schema_version": item.get("schema_version", "ai_intel_v1"),
            "producer": item.get("producer", "member-a"),
            "generated_at": item.get("generated_at", _now_iso()),
        }


class EventEvidenceScorer(EDTModule):
    """A1: evidence scoring for AI event intelligence."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("EventEvidenceScorer", "1.0.0", config_path or _default_config_path())

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        source_url = raw.get("source_url", "")
        source_type = (raw.get("source_type") or "").lower()
        timestamp = raw.get("timestamp")
        corroborating_sources = raw.get("corroborating_sources", [])

        evidence_score = self._score_evidence(source_url, source_type)
        consistency_score = min(100, 50 + 10 * len(corroborating_sources))
        freshness_score = self._score_freshness(timestamp)
        confidence = round(0.4 * evidence_score + 0.3 * consistency_score + 0.3 * freshness_score, 2)

        narrative_state = raw.get("narrative_state", "initial")
        reasoning = [
            f"source_type={source_type or 'unknown'}",
            f"corroborating_sources={len(corroborating_sources)}",
            f"freshness_score={freshness_score}",
        ]

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "trace_id": raw.get("trace_id", _new_trace_id()),
                "event_id": raw.get("event_id", ""),
                "evidence_score": evidence_score,
                "consistency_score": consistency_score,
                "freshness_score": freshness_score,
                "confidence": confidence,
                "narrative_state": narrative_state,
                "reasoning": reasoning,
                "schema_version": raw.get("schema_version", "ai_intel_v1"),
                "producer": raw.get("producer", "member-a"),
                "generated_at": raw.get("generated_at", _now_iso()),
            },
        )

    def _score_evidence(self, source_url: str, source_type: str) -> float:
        rank_map = self._get_config("modules.EventEvidenceScorer.params.source_rank_map", {})
        default_score = float(self._get_config("modules.EventEvidenceScorer.params.default_score", 50))
        abnormal_domains = [d.lower() for d in self._get_config("modules.EventEvidenceScorer.params.abnormal_domains", [])]
        abnormal_types = [t.lower() for t in self._get_config("modules.EventEvidenceScorer.params.abnormal_types", [])]
        abnormal_penalty = float(self._get_config("modules.EventEvidenceScorer.params.abnormal_penalty", 20))

        host = urlparse(source_url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        score = default_score
        for _, cfg in rank_map.items():
            domains = [d.lower() for d in cfg.get("domains", [])]
            if any(d in host for d in domains):
                score = float(cfg.get("score", default_score))
                break
        if source_type == "official":
            score = max(score, 90.0)
        elif source_type == "social":
            score = min(score, 30.0)

        if any(d in host for d in abnormal_domains) or source_type in abnormal_types:
            score = max(0.0, score - abnormal_penalty)
        return score

    def _score_freshness(self, timestamp: Optional[str]) -> float:
        if not timestamp:
            return 50.0
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except Exception:
            return 50.0
        hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        if hours <= 1:
            return 90.0
        if hours <= 6:
            return 80.0
        if hours <= 24:
            return 60.0
        if hours <= 72:
            return 40.0
        return 20.0


if __name__ == "__main__":
    ingestion = NewsIngestion()
    out = ingestion.run({"max_items": 2})
    print(out.data)
    scorer = EventEvidenceScorer()
    sample = out.data["items"][0]
    print(scorer.run(sample).data)
