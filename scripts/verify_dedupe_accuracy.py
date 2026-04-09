#!/usr/bin/env python3
"""Verify news dedupe behavior with deterministic fixtures."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import List, Dict, Any

from ai_event_intel import NewsIngestion


def _sample_items() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "headline": "Fed signals rate cuts ahead as inflation cools",
            "timestamp": now,
            "source_url": "https://a.example.com",
            "raw_text": "a",
        },
        {
            "headline": "Fed signals rate cuts ahead as inflation cools further",
            "timestamp": now,
            "source_url": "https://b.example.com",
            "raw_text": "b",
        },
        {
            "headline": "Oil rises after supply disruption in key region",
            "timestamp": now,
            "source_url": "https://c.example.com",
            "raw_text": "c",
        },
        {
            "headline": "Oil rises after supply disruption in key region",
            "timestamp": now,
            "source_url": "https://d.example.com",
            "raw_text": "d",
        },
        {
            "headline": "NVIDIA launches new AI accelerator chip",
            "timestamp": now,
            "source_url": "https://e.example.com",
            "raw_text": "e",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dedupe accuracy")
    parser.add_argument("--min-accuracy", type=float, default=0.95, help="minimum expected dedupe accuracy")
    args = parser.parse_args()

    items = _sample_items()
    ingestion = NewsIngestion()
    out = ingestion.run(
        {
            "items_override": items,
            "max_items": 20,
            "dedupe": True,
            "dedupe_window_minutes": 120,
            "dedupe_similarity_threshold": 0.78,
            "dedupe_min_token_overlap": 3,
        }
    )
    deduped = out.data.get("items", [])

    expected_unique = 3
    observed_unique = len(deduped)
    total_items = len(items)
    expected_removed = total_items - expected_unique
    observed_removed = total_items - observed_unique
    accuracy = 1.0 - (abs(observed_removed - expected_removed) / max(1, total_items))

    deduped_headlines = [str(item.get("headline", "")).lower() for item in deduped]
    semantics_ok = (
        sum("fed signals rate cuts" in h for h in deduped_headlines) == 1
        and sum("oil rises after supply disruption" in h for h in deduped_headlines) == 1
        and sum("nvidia launches new ai accelerator chip" in h for h in deduped_headlines) == 1
    )
    passed = accuracy >= args.min_accuracy and semantics_ok

    report = {
        "total_items": total_items,
        "expected_unique": expected_unique,
        "observed_unique": observed_unique,
        "expected_removed": expected_removed,
        "observed_removed": observed_removed,
        "accuracy": round(accuracy, 4),
        "semantics_ok": semantics_ok,
        "min_accuracy": args.min_accuracy,
        "passed": passed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
