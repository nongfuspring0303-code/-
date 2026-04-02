#!/usr/bin/env python3
"""
T5.2 Multi-event concurrency arbitration.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import yaml

from full_workflow_runner import FullWorkflowRunner


class MultiEventArbiter:
    """Batch runner with priority, dedup, and conflict control."""

    def __init__(self, config_path: str | None = None):
        self.config_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml"
        self.runner = FullWorkflowRunner()
        self.config = self._load_config()
        self.max_open_events = int(
            self.config.get("modules", {}).get("PositionSizer", {}).get("params", {}).get("daily", {}).get("max_open_events", 5)
        )

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError, TypeError, ValueError) as exc:
            logging.warning("Failed to load arbiter config; fallback to defaults: %s", exc)
            return {}

    @staticmethod
    def _event_key(event: Dict[str, Any]) -> str:
        headline = str(event.get("headline", "")).strip().lower()
        source = str(event.get("source", "")).strip()
        parsed = urlparse(source)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/").lower()
        normalized_source = f"{host}{path}" if host else source.lower()
        return f"{headline}|{normalized_source}"

    @staticmethod
    def _severity_weight(event: Dict[str, Any]) -> int:
        sev = event.get("severity")
        mapping = {"E4": 5, "E3": 4, "E2": 3, "E1": 2, "E0": 1}
        if sev in mapping:
            return mapping[sev]
        vix = float(event.get("vix", 0))
        if vix >= 40:
            return 5
        if vix >= 25:
            return 4
        if vix >= 20:
            return 3
        return 2

    @staticmethod
    def _timestamp_weight(event: Dict[str, Any]) -> float:
        ts = event.get("timestamp")
        if not ts:
            return datetime.now(timezone.utc).timestamp()
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except Exception:
            return datetime.now(timezone.utc).timestamp()

    @staticmethod
    def _ensure_request_id(event: Dict[str, Any]) -> str:
        base = f"{event.get('headline','')}|{event.get('source','')}|{event.get('timestamp','')}"
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12].upper()
        return event.get("request_id") or f"REQ-{digest}"

    def _dedup_events(self, events: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        seen = set()
        deduped = []
        dropped = 0
        for e in events:
            key = self._event_key(e)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            deduped.append(e)
        return deduped, dropped

    def _prioritize(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            events,
            key=lambda e: (self._severity_weight(e), self._timestamp_weight(e)),
            reverse=True,
        )

    def run_batch(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        prioritized = self._prioritize(events)
        deduped, dropped_dedup = self._dedup_events(prioritized)

        results = []
        symbol_inflight = set()
        accepted_count = 0
        dropped_conflict = 0

        for e in deduped:
            request_id = self._ensure_request_id(e)
            symbol = e.get("symbol", "UNKNOWN")

            if accepted_count >= self.max_open_events:
                dropped_conflict += 1
                results.append(
                    {
                        "request_id": request_id,
                        "symbol": symbol,
                        "status": "SKIPPED",
                        "reason": "MAX_OPEN_EVENTS_REACHED",
                    }
                )
                continue

            if symbol in symbol_inflight:
                dropped_conflict += 1
                results.append(
                    {
                        "request_id": request_id,
                        "symbol": symbol,
                        "status": "SKIPPED",
                        "reason": "SYMBOL_CONFLICT_IN_BATCH",
                    }
                )
                continue

            payload = dict(e)
            payload["request_id"] = request_id
            out = self.runner.run(payload)
            action = out["execution"]["final"]["action"]
            if action == "EXECUTE":
                symbol_inflight.add(symbol)
                accepted_count += 1

            results.append(
                {
                    "request_id": request_id,
                    "symbol": symbol,
                    "status": "DONE",
                    "final_action": action,
                    "score": out["execution"]["final"].get("score"),
                    "position_notional": out["execution"]["final"].get("position_notional"),
                }
            )

        return {
            "total_input": len(events),
            "processed": len(deduped),
            "dropped_dedup": dropped_dedup,
            "dropped_conflict": dropped_conflict,
            "executed": accepted_count,
            "results": results,
        }


if __name__ == "__main__":
    now = datetime.now(timezone.utc).isoformat()
    sample = [
        {
            "headline": "Fed emergency liquidity action",
            "source": "https://www.reuters.com/markets/us/example1",
            "timestamp": now,
            "symbol": "XLF",
            "vix": 32,
            "vix_change_pct": 28,
            "spx_move_pct": 2.1,
            "sector_move_pct": 3.0,
            "entry_price": 42.5,
            "risk_per_share": 1.5,
            "direction": "long",
        },
        {
            "headline": "Fed emergency liquidity action",
            "source": "https://www.reuters.com/markets/us/example1",
            "timestamp": now,
            "symbol": "XLF",
            "vix": 32,
        },
        {
            "headline": "Trade tariff escalation in key sector",
            "source": "https://www.reuters.com/markets/us/example2",
            "timestamp": now,
            "symbol": "XLI",
            "vix": 24,
            "entry_price": 100,
            "risk_per_share": 2,
            "direction": "long",
        },
    ]
    out = MultiEventArbiter().run_batch(sample)
    print(json.dumps(out, indent=2, ensure_ascii=False))

