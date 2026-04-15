#!/usr/bin/env python3
"""Compare a current acceptance report against a stored baseline.

Reports regression metrics:
  - New failures (failed now, passed before)
  - Fixed failures (passed now, failed before)
  - Metric deltas (chain_completeness, direction_consistency, etc.)
  - Overall merge recommendation

Usage:
  python compare_acceptance_baseline.py \
    --current logs/acceptance/latest_acceptance_report.json \
    --baseline tests/acceptance/baseline_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

KEY_METRICS = [
    "chain_completeness_rate",
    "required_fields_missing_rate",
    "direction_consistency_rate",
    "path_consistency_rate",
    "high_risk_false_release_rate",
]


@dataclass
class CaseStatus:
    case_id: str
    baseline: str  # "PASS" | "FAIL"
    current: str
    delta: str  # "stable" | "new_fail" | "fixed_fail"


@dataclass
class ComparisonReport:
    baseline_label: str = "baseline"
    current_label: str = "current"
    case_deltas: List[CaseStatus] = field(default_factory=list)
    new_failures: List[str] = field(default_factory=list)
    fixed_failures: List[str] = field(default_factory=list)
    baseline_metrics: Dict[str, float] = field(default_factory=dict)
    current_metrics: Dict[str, float] = field(default_factory=dict)
    metric_deltas: Dict[str, float] = field(default_factory=dict)
    merge_recommended: bool = True
    reasons: List[str] = field(default_factory=list)


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _case_passed(item: Dict[str, Any]) -> bool:
    return bool(item.get("final", False))


def compare(baseline: Dict[str, Any], current: Dict[str, Any]) -> ComparisonReport:
    report = ComparisonReport()

    baseline_cases = {c["case_id"]: c for c in baseline.get("case_results", [])}
    current_cases = {c["case_id"]: c for c in current.get("case_results", [])}

    all_ids = sorted(set(list(baseline_cases.keys()) + list(current_cases.keys())))

    for cid in all_ids:
        b = baseline_cases.get(cid)
        c = current_cases.get(cid)

        b_pass = _case_passed(b) if b else False
        c_pass = _case_passed(c) if c else False

        if b_pass and not c_pass:
            delta = "new_fail"
            report.new_failures.append(cid)
        elif not b_pass and c_pass:
            delta = "fixed_fail"
            report.fixed_failures.append(cid)
        else:
            delta = "stable"

        report.case_deltas.append(CaseStatus(
            case_id=cid,
            baseline="PASS" if b_pass else "FAIL",
            current="PASS" if c_pass else "FAIL",
            delta=delta,
        ))

    # Metric deltas
    b_metrics = baseline.get("summary", {}).get("metrics", {})
    c_metrics = current.get("summary", {}).get("metrics", {})
    report.baseline_metrics = {k: b_metrics.get(k, 0.0) for k in KEY_METRICS}
    report.current_metrics = {k: c_metrics.get(k, 0.0) for k in KEY_METRICS}

    for k in KEY_METRICS:
        b_val = b_metrics.get(k, 0.0)
        c_val = c_metrics.get(k, 0.0)
        # For "higher is better" metrics, positive delta is good
        # For "lower is better" (missing_rate, false_release_rate), negative delta is good
        report.metric_deltas[k] = round(c_val - b_val, 6)

    # Merge recommendation
    if report.new_failures:
        report.merge_recommended = False
        report.reasons.append(
            f"Regression: {len(report.new_failures)} new failure(s): {', '.join(report.new_failures)}"
        )

    thresholds = current.get("summary", {}).get("thresholds", {})
    threshold_pass = current.get("summary", {}).get("threshold_pass", False)
    if not threshold_pass:
        report.merge_recommended = False
        report.reasons.append("Current run does not meet acceptance thresholds")

    if not report.reasons:
        if report.fixed_failures:
            report.reasons.append(
                f"Improved: {len(report.fixed_failures)} previously failing case(s) now pass"
            )
        else:
            report.reasons.append("No regression detected; all cases stable")

    return report


def _print_table(report: ComparisonReport) -> None:
    header = f"{'CASE_ID':30} {'BASELINE':9} {'CURRENT':9} {'DELTA':12}"
    print(header)
    print("-" * 60)
    for item in report.case_deltas:
        print(f"{item.case_id:30} {item.baseline:9} {item.current:9} {item.delta:12}")

    print("\n" + "=" * 60)
    print("Metric Comparison:")
    for k in KEY_METRICS:
        b_val = report.baseline_metrics[k]
        c_val = report.current_metrics[k]
        d = report.metric_deltas[k]
        sign = "+" if d > 0 else ""
        print(f"  {k:35} baseline={b_val:.4f}  current={c_val:.4f}  delta={sign}{d:.6f}")

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  New failures:   {len(report.new_failures)}")
    if report.new_failures:
        for c in report.new_failures:
            print(f"    - {c}")
    print(f"  Fixed failures: {len(report.fixed_failures)}")
    if report.fixed_failures:
        for c in report.fixed_failures:
            print(f"    - {c}")

    print(f"\n  Merge recommended: {'YES' if report.merge_recommended else 'NO'}")
    for r in report.reasons:
        print(f"    -> {r}")


def _to_dict(report: ComparisonReport) -> Dict[str, Any]:
    return {
        "baseline_label": report.baseline_label,
        "current_label": report.current_label,
        "case_deltas": [
            {
                "case_id": c.case_id,
                "baseline": c.baseline,
                "current": c.current,
                "delta": c.delta,
            }
            for c in report.case_deltas
        ],
        "new_failures": report.new_failures,
        "fixed_failures": report.fixed_failures,
        "baseline_metrics": report.baseline_metrics,
        "current_metrics": report.current_metrics,
        "metric_deltas": report.metric_deltas,
        "merge_recommended": report.merge_recommended,
        "reasons": report.reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare acceptance report against baseline")
    parser.add_argument("--current", required=True, help="Path to current acceptance report JSON")
    parser.add_argument("--baseline", required=True, help="Path to baseline JSON")
    parser.add_argument("--output", default=None, help="Optional: save comparison JSON to this path")
    args = parser.parse_args()

    baseline = _load_json(args.baseline)
    current = _load_json(args.current)

    report = compare(baseline, current)
    _print_table(report)

    if args.output:
        data = _to_dict(report)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, ensure_ascii=False, indent=2, fp=f)
        print(f"\nComparison saved to: {args.output}")

    return 0 if report.merge_recommended else 1


if __name__ == "__main__":
    raise SystemExit(main())
