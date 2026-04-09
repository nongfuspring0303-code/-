#!/usr/bin/env python3
"""
Decision Card module for C4 - Decision card generation and archival.
- Generate decision cards with evidence, counter-evidence, risk notes
- Archive by trace_id for later retrieval
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import yaml


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _default_archive_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "logs" / "decision_cards")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class DecisionCard:
    trace_id: str
    event_id: str
    summary: str
    evidence: List[str] = field(default_factory=list)
    counter_evidence: List[str] = field(default_factory=list)
    risk_notes: List[str] = field(default_factory=list)
    trigger_conditions: List[str] = field(default_factory=list)
    invalid_conditions: List[str] = field(default_factory=list)
    schema_version: str = "1.0.0"
    producer: str = "EDT-System"
    generated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "event_id": self.event_id,
            "summary": self.summary,
            "evidence": self.evidence,
            "counter_evidence": self.counter_evidence,
            "risk_notes": self.risk_notes,
            "trigger_conditions": self.trigger_conditions,
            "invalid_conditions": self.invalid_conditions,
            "schema_version": self.schema_version,
            "producer": self.producer,
            "generated_at": self.generated_at,
        }


class DecisionCardGenerator:
    def __init__(self, archive_dir: str | None = None, config_path: str | None = None):
        self.archive_dir = Path(archive_dir) if archive_dir else Path(_default_archive_dir())
        self.config_path = Path(config_path) if config_path else Path(_default_config_path())
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.archive_dir / "index.json"
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError, TypeError, ValueError):
            return {}

    def _get_config(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        val = self._config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def generate(self, trace_id: str, event_id: str, summary: str,
                 evidence: List[str] = None, counter_evidence: List[str] = None,
                 risk_notes: List[str] = None, trigger_conditions: List[str] = None,
                 invalid_conditions: List[str] = None, producer: str = "EDT-System") -> DecisionCard:
        default_producer = self._get_config("modules.DecisionCardGenerator.params.producer", "EDT-System")
        schema_version = self._get_config("modules.DecisionCardGenerator.params.schema_version", "v1.0")

        card = DecisionCard(
            trace_id=trace_id,
            event_id=event_id,
            summary=summary,
            evidence=evidence or [],
            counter_evidence=counter_evidence or [],
            risk_notes=risk_notes or [],
            trigger_conditions=trigger_conditions or [],
            invalid_conditions=invalid_conditions or [],
            producer=producer or default_producer,
            schema_version=schema_version,
            generated_at=_now_iso(),
        )
        self._archive(card)
        return card

    def _archive(self, card: DecisionCard) -> None:
        card_file = self.archive_dir / f"{card.trace_id}.json"
        with open(card_file, "w", encoding="utf-8") as f:
            json.dump(card.to_dict(), f, ensure_ascii=False, indent=2)
        self._update_index(card.trace_id, card.event_id, card.generated_at)

    def _update_index(self, trace_id: str, event_id: str, generated_at: str) -> None:
        index = {}
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                index = {}

        index[trace_id] = {
            "event_id": event_id,
            "generated_at": generated_at,
            "file": f"{trace_id}.json",
        }

        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)

    def get_card(self, trace_id: str) -> Optional[Dict[str, Any]]:
        card_file = self.archive_dir / f"{trace_id}.json"
        if not card_file.exists():
            return None

        with open(card_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_cards(self, limit: int = 50) -> List[str]:
        if not self.index_file.exists():
            return []

        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            cards = list(index.keys())
            cards.sort(reverse=True)
            return cards[:limit]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return []

    def search_by_event_id(self, event_id: str) -> List[Dict[str, Any]]:
        if not self.index_file.exists():
            return []

        results = []
        with open(self.index_file, "r", encoding="utf-8") as f:
            index = json.load(f)

        for trace_id, info in index.items():
            if info.get("event_id") == event_id:
                card = self.get_card(trace_id)
                if card:
                    results.append(card)

        return results


if __name__ == "__main__":
    gen = DecisionCardGenerator()
    
    card = gen.generate(
        trace_id="TRC-20260402-ABC123",
        event_id="EVT-US-TECH-RALLY",
        summary="Strong bullish signal from tech sector earnings beat",
        evidence=[
            "NVIDIA earnings beat by 15%",
            "AI infrastructure spending accelerating",
            "Institutional buying increased 20%",
        ],
        counter_evidence=[
            "Valuation already high",
            "Fed rate uncertainty",
        ],
        risk_notes=[
            "Max drawdown risk: 8%",
            "Market volatility elevated",
        ],
        trigger_conditions=[
            "A1 >= 60",
            "liquidity_check passed",
        ],
        invalid_conditions=[
            "severity drops to E0",
            "fatigue > 80%",
        ],
    )
    
    print(f"Generated card: {card.trace_id}")
    print(f"Summary: {card.summary}")
    
    retrieved = gen.get_card(card.trace_id)
    print(f"Retrieved: {retrieved is not None}")
