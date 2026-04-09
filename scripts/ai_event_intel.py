#!/usr/bin/env python3
"""
AI event intelligence modules for A-layer.
- NewsIngestion (A0)
- EventEvidenceScorer (A1)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import time
import uuid
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import hashlib
from email.utils import parsedate_to_datetime

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus
from pathlib import Path
from intel_modules import SourceRankerModule


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
    except (TypeError, ValueError):
        try:
            return parsedate_to_datetime(ts)
        except (TypeError, ValueError):
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
    items.sort(key=lambda x: _parse_datetime(x.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


def _parse_atom(xml_text: str, source_url: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    ns = "{http://www.w3.org/2005/Atom}"
    items = []
    for entry in root.findall(f".//{ns}entry"):
        title = (entry.findtext(f"{ns}title") or "").strip()
        link = ""
        link_el = entry.find(f"{ns}link")
        if link_el is not None:
            link = link_el.attrib.get("href", "")
        updated = (entry.findtext(f"{ns}updated") or "").strip()
        summary = (entry.findtext(f"{ns}summary") or entry.findtext(f"{ns}content") or "").strip()
        if not title:
            continue
        items.append(
            {
                "headline": title,
                "source_url": link or source_url,
                "timestamp": updated,
                "raw_text": summary,
                "source_type": "atom",
            }
        )
    items.sort(key=lambda x: _parse_datetime(x.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


def _safe_fetch(url: str, timeout: int) -> Optional[str]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "EDT-AI/1.0 (contact: admin@example.com) Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    current = []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _jaccard(a: List[str], b: List[str]) -> float:
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _deterministic_event_id(headline: str, source_url: str, timestamp: str) -> str:
    dt = _parse_datetime(timestamp)
    date_part = dt.strftime("%Y%m%d") if dt else "00000000"
    base = f"{headline}|{source_url}|{date_part}".encode("utf-8", errors="ignore")
    digest = hashlib.sha1(base).hexdigest()[:10]
    return f"ME-{date_part}-{digest}"


def _dedupe_items(
    items: List[Dict[str, Any]],
    window_minutes: int,
    similarity_threshold: float = 0.78,
    min_token_overlap: int = 3,
) -> List[Dict[str, Any]]:
    seen: List[Dict[str, Any]] = []
    token_index: Dict[str, List[int]] = defaultdict(list)
    output: List[Dict[str, Any]] = []
    window_seconds = max(1, window_minutes) * 60

    for item in items:
        headline = (item.get("headline") or "").strip()
        host = urlparse(item.get("source_url", "")).netloc.lower().replace("www.", "")
        dt = _parse_datetime(item.get("timestamp"))
        tokens = _tokenize(headline)

        is_dup = False
        if tokens:
            candidate_indexes = set()
            for token in set(tokens):
                candidate_indexes.update(token_index.get(token, []))
        else:
            candidate_indexes = set(range(len(seen)))

        for idx in candidate_indexes:
            prior = seen[idx]
            prior_dt = prior["dt"]
            if dt and prior_dt and abs((dt - prior_dt).total_seconds()) > window_seconds:
                continue
            if prior["headline"] == headline and prior["host"] == host:
                is_dup = True
                break
            overlap = len(set(tokens) & set(prior["tokens"]))
            if overlap >= min_token_overlap:
                score = _jaccard(tokens, prior["tokens"])
                if score >= similarity_threshold:
                    is_dup = True
                    break

        if is_dup:
            continue
        seen.append({"headline": headline, "host": host, "dt": dt, "tokens": tokens})
        seen_idx = len(seen) - 1
        for token in set(tokens):
            token_index[token].append(seen_idx)
        output.append(item)
    return output


class NewsIngestion(EDTModule):
    """A0: real news ingestion with fallback and standardization."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("NewsIngestion", "1.0.0", config_path or _default_config_path())
        self._ranker = None
        if bool(self._get_config("modules.NewsIngestion.params.enable_source_rank", True)):
            try:
                self._ranker = SourceRankerModule(config_path or _default_config_path())
            except (TypeError, ValueError):
                self._ranker = None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        items_override = raw.get("items_override")
        max_items = int(raw.get("max_items", 10))

        if items_override:
            normalized = [self._normalize_item(item) for item in items_override]
            dedupe_on = bool(self._get_config("modules.NewsIngestion.params.dedupe", True))
            window_minutes = int(self._get_config("modules.NewsIngestion.params.dedupe_window_minutes", 120))
            similarity_threshold = float(self._get_config("modules.NewsIngestion.params.dedupe_similarity_threshold", 0.78))
            min_token_overlap = int(self._get_config("modules.NewsIngestion.params.dedupe_min_token_overlap", 3))
            if dedupe_on:
                normalized = _dedupe_items(normalized, window_minutes, similarity_threshold, min_token_overlap)
            return ModuleOutput(status=ModuleStatus.SUCCESS, data={"items": normalized[:max_items]})

        sources = raw.get("sources") or self._get_config("modules.NewsIngestion.params.sources", [])
        timeout = int(raw.get("timeout", self._get_config("modules.NewsIngestion.params.timeout", 8)))
        retries = int(raw.get("retries", self._get_config("modules.NewsIngestion.params.retries", 2)))

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
                root = ET.fromstring(xml_text)
                if root.tag.endswith("feed"):
                    items.extend(_parse_atom(xml_text, src))
                else:
                    items.extend(_parse_rss(xml_text, src))
            except Exception:
                continue

        if not items:
            execution_mode = str(self._get_config("modules.ExecutionAdapter.params.mode", "dry_run")).lower()
            runtime_role = str(self._get_config("runtime.role", "dev")).lower()
            strict_fallback = bool(self._get_config("runtime.strict_fallback", False)) or bool(
                self._get_config("modules.NewsIngestion.params.strict_fallback", False)
            )
            if execution_mode == "live" or runtime_role == "prod" or strict_fallback:
                return ModuleOutput(
                    status=ModuleStatus.FAILED,
                    data={"items": []},
                    errors=[
                        {
                            "code": "NEWS_SOURCE_UNAVAILABLE",
                            "message": "News source fetch yielded no items; strict mode blocks fallback.",
                        }
                    ],
                )
            items = [
                {
                    "headline": "Fed announces emergency liquidity action",
                    "source_url": "https://www.federalreserve.gov/",
                    "timestamp": _now_iso(),
                    "raw_text": "Fallback news item used when sources fail.",
                    "source_type": "fallback",
                    "is_fallback": True,
                    "is_test_data": True,  # 标记为测试数据
                }
            ]

        normalized = [self._normalize_item(item) for item in items]
        dedupe_on = bool(self._get_config("modules.NewsIngestion.params.dedupe", True))
        window_minutes = int(self._get_config("modules.NewsIngestion.params.dedupe_window_minutes", 120))
        similarity_threshold = float(self._get_config("modules.NewsIngestion.params.dedupe_similarity_threshold", 0.78))
        min_token_overlap = int(self._get_config("modules.NewsIngestion.params.dedupe_min_token_overlap", 3))
        if dedupe_on:
            normalized = _dedupe_items(normalized, window_minutes, similarity_threshold, min_token_overlap)
        return ModuleOutput(status=ModuleStatus.SUCCESS, data={"items": normalized[:max_items]})

    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = item.get("trace_id") or _new_trace_id()
        timestamp = _normalize_timestamp(item.get("timestamp"))
        source_url = item.get("source_url", "")
        source_rank = item.get("source_rank", "")
        if self._ranker and source_url:
            try:
                rank_out = self._ranker.run({"source_url": source_url})
                source_rank = rank_out.data.get("rank", source_rank)
            except (AttributeError, TypeError, ValueError):
                pass
        event_id = item.get("event_id") or _deterministic_event_id(
            item.get("headline", ""),
            source_url,
            timestamp,
        )
        return {
            "trace_id": trace_id,
            "event_id": event_id,
            "headline": item.get("headline", ""),
            "source_url": source_url,
            "timestamp": timestamp,
            "raw_text": item.get("raw_text", ""),
            "source_type": item.get("source_type", ""),
            "source_rank": source_rank,
            "is_test_data": bool(item.get("is_test_data", False)),
            "metadata": item.get("metadata", {}),
            "schema_version": item.get("schema_version", "v1.0"),
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
        consistency_score = self._score_consistency(corroborating_sources)
        freshness_score = self._score_freshness(timestamp, raw.get("generated_at") or raw.get("evaluated_at"))
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
                "schema_version": raw.get("schema_version", "v1.0"),
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
            if any(host == d or host.endswith("." + d) for d in domains):
                score = float(cfg.get("score", default_score))
                break
        if source_type == "official":
            score = max(score, 90.0)
        elif source_type == "social":
            score = min(score, 30.0)

        if any(host == d or host.endswith("." + d) for d in abnormal_domains) or source_type in abnormal_types:
            score = max(0.0, score - abnormal_penalty)
        return score

    def _score_consistency(self, corroborating_sources: Any) -> float:
        if not corroborating_sources:
            return 50.0
        weights = self._get_config("modules.EventEvidenceScorer.params.consistency_rank_weights", {})
        weights = {k.lower(): float(v) for k, v in weights.items()}
        default_weight = float(weights.get("unknown", 0.5))

        if isinstance(corroborating_sources, list) and corroborating_sources and isinstance(corroborating_sources[0], dict):
            total = 0.0
            for src in corroborating_sources:
                rank = str(src.get("source_rank", "unknown")).lower()
                total += float(weights.get(rank, default_weight))
            return min(100.0, 50.0 + 10.0 * total)

        return min(100.0, 50.0 + 10.0 * len(corroborating_sources))

    def _score_freshness(self, timestamp: Optional[str], reference_ts: Optional[str] = None) -> float:
        if not timestamp:
            return 50.0
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return 50.0
        now_dt = None
        if reference_ts:
            try:
                now_dt = datetime.fromisoformat(reference_ts.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                now_dt = None
        if not now_dt:
            now_dt = datetime.now(timezone.utc)
        hours = (now_dt - dt).total_seconds() / 3600
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
