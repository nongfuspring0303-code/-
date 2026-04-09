#!/usr/bin/env python3
"""Verify the Reuters canary source health gate."""

from __future__ import annotations

import argparse
import json
import sys

from canary_source_health import CanarySourceHealth


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Reuters canary source health.")
    parser.add_argument("--refresh", action="store_true", help="Fetch a fresh canary sample before verifying.")
    parser.add_argument("--config", type=str, default=None, help="Config path override.")
    parser.add_argument("--audit-dir", type=str, default=None, help="Audit directory override.")
    args = parser.parse_args()

    health = CanarySourceHealth(config_path=args.config, audit_dir=args.audit_dir)
    if args.refresh:
        health.collect_once()

    summary = health.read_summary()
    assessment = health.assess(summary=summary, mode="prod")
    print(json.dumps({
        "status": assessment.status,
        "summary": assessment.summary,
        "warnings": assessment.warnings,
        "errors": assessment.errors,
        "evidence": assessment.evidence,
        "windows": assessment.windows,
    }, ensure_ascii=False, indent=2))
    return 0 if assessment.status == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
