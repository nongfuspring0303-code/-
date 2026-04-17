#!/usr/bin/env python3
"""Summarize acceptance results into a concise dashboard.

Reads the latest acceptance report and prints:
  - Overall threshold pass/fail
  - Per-category pass rate
  - Top failing assertions (if any)
  - 6 core metrics vs thresholds

Usage:
  python summarize_acceptance_results.py
  python summarize_acceptance_results.py --report logs/acceptance/latest_acceptance_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "logs" / "acceptance" / "latest_acceptance_report.json"


def _load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _pass_text(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def summarize(report: Dict[str, Any]) -> None:
    summary = report.get("summary", {})
    cases = report.get("case_results", [])
    metrics = summary.get("metrics", {})
    thresholds = summary.get("thresholds", {})
    threshold_pass = summary.get("threshold_pass", False)

    total = summary.get("total_cases", 0)
    passed = summary.get("passed_cases", 0)
    failed = summary.get("failed_cases", 0)

    print("=" * 72)
    print("  ACCEPTANCE SUMMARY")
    print("=" * 72)
    print(f"  Generated:   {summary.get('generated_at', 'N/A')}")
    print(f"  Total:       {total}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"  Threshold:   {_pass_text(threshold_pass)}")
    print()

    # Metrics vs thresholds
    print("  CORE METRICS vs THRESHOLDS:")
    print("  " + "-" * 68)
    metric_checks = [
        ("chain_completeness_rate", ">=", "chain_completeness_min", True),
        ("required_fields_missing_rate", "<=", "required_fields_missing_rate_max", False),
        ("direction_consistency_rate", ">=", "direction_consistency_min", True),
        ("path_consistency_rate", ">=", "path_consistency_min", True),
        ("high_risk_false_release_rate", "<=", "high_risk_false_release_max", False),
    ]
    for metric_key, op, thresh_key, higher_better in metric_checks:
        val = metrics.get(metric_key, 0.0)
        thresh = thresholds.get(thresh_key, 0.0)
        if higher_better:
            ok = val >= thresh
        else:
            ok = val <= thresh
        bar_len = int(val * 30)
        bar = "#" * bar_len
        print(f"  {metric_key:40} {val:.4f} {op} {thresh:.2f}  [{_pass_text(ok):4}] {bar}")
    print()

    # Per-category breakdown
    print("  PER-CATEGORY PASS RATE:")
    print("  " + "-" * 68)
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for c in cases:
        cid = c["case_id"]
        # Extract category from case_id prefix
        parts = cid.split("_")
        cat = parts[0] if parts else "unknown"
        by_cat.setdefault(cat, []).append(c)

    for cat in sorted(by_cat):
        cat_cases = by_cat[cat]
        cat_passed = sum(1 for c in cat_cases if c.get("final"))
        cat_total = len(cat_cases)
        rate = cat_passed / cat_total if cat_total > 0 else 0.0
        print(f"  {cat:20} {cat_passed}/{cat_total}  ({rate:.0%})")
    print()

    # Failed cases detail
    failed_cases = [c for c in cases if not c.get("final")]
    if failed_cases:
        print("  FAILING CASES:")
        print("  " + "-" * 68)
        for c in failed_cases:
            details = c.get("details", {})
            failures = []
            if not c.get("chain_ok"):
                failures.append("CHAIN")
            if not c.get("fields_ok"):
                failures.append("FIELDS")
            if not c.get("path_ok"):
                failures.append("PATH")
            if not c.get("signal_ok"):
                failures.append("SIGNAL")
            if not c.get("risk_ok"):
                failures.append("RISK")
            if not c.get("mixed_regime_ok"):
                failures.append("MIXED_REGIME")
            print(f"  {c['case_id']:30} failed: {', '.join(failures)}")
            if "risk_meta" in details:
                rm = details["risk_meta"]
                print(f"    -> risk: actual={rm.get('actual', '?')}, max_expected={rm.get('max_expected', '?')}")
            if "actual_path_type" in details:
                print(f"    -> path: actual={details['actual_path_type']}")
            if "mixed_regime_check" in details:
                mr = details["mixed_regime_check"]
                print(f"    -> mixed_regime: ok={mr.get('ok', '?')}, reason={mr.get('reason', '?')}")
        print()

    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize acceptance results")
    parser.add_argument("--report", default=None, help="Path to acceptance report JSON")
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else DEFAULT_REPORT
    if not report_path.exists():
        print(f"Error: report not found at {report_path}", file=sys.stderr)
        return 1

    report = _load(report_path)
    summarize(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
