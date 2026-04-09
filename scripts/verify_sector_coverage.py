#!/usr/bin/env python3
"""Verify sector mapping coverage against required sector universe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Set

import yaml


def _default_mapping_path() -> Path:
    return Path(__file__).resolve().parent.parent / "configs" / "sector_impact_mapping.yaml"


def _required_sectors() -> Set[str]:
    return {
        "Technology",
        "Financial Services",
        "Healthcare",
        "Industrials",
        "Energy",
        "Consumer Cyclical",
    }


def _load_mapping(path: Path) -> Dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mapping = payload.get("mapping", {})
    if isinstance(mapping, dict):
        return mapping
    return {}


def _collect_available_sectors(mapping: Dict[str, object]) -> Set[str]:
    available: Set[str] = set()
    for key, values in mapping.items():
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"Invalid mapping entry for '{key}': expected list[str]")
        available.update(values)
    return available


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify sector coverage")
    parser.add_argument("--mapping", default=str(_default_mapping_path()), help="sector mapping yaml path")
    parser.add_argument("--min-coverage", type=float, default=0.90, help="minimum coverage ratio")
    args = parser.parse_args()

    mapping = _load_mapping(Path(args.mapping))
    required = _required_sectors()
    try:
        available = _collect_available_sectors(mapping)
    except ValueError as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    covered = sorted(required & available)
    missing = sorted(required - available)

    coverage_rate = round((len(covered) / len(required)) if required else 1.0, 4)
    passed = coverage_rate >= args.min_coverage

    report = {
        "required_count": len(required),
        "covered_count": len(covered),
        "coverage_rate": coverage_rate,
        "min_coverage": args.min_coverage,
        "missing": missing,
        "passed": passed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
