#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

from config_center import ConfigCenter


def compare_shadow(a_records: List[Dict[str, Any]], b_records: List[Dict[str, Any]]) -> Dict[str, float]:
    paired = []
    by_trace = {str(item.get("trace_id", "")): item for item in b_records}
    for a in a_records:
        tid = str(a.get("trace_id", ""))
        b = by_trace.get(tid)
        if tid and b is not None:
            paired.append((a, b))

    if not paired:
        return {
            "samples": 0,
            "action_match_rate": 0.0,
            "path_match_rate": 0.0,
            "sector_match_rate": 0.0,
            "score_delta_p95": 0.0,
        }

    action_match = 0
    path_match = 0
    sector_match = 0
    deltas: List[float] = []

    for a, b in paired:
        if str(a.get("action", "")) == str(b.get("action", "")):
            action_match += 1
        if str((a.get("dominant_path") or {}).get("name", "")) == str((b.get("dominant_path") or {}).get("name", "")):
            path_match += 1
        if str((a.get("sector_rankings") or {}).get("primary_sector", "")) == str(
            (b.get("sector_rankings") or {}).get("primary_sector", "")
        ):
            sector_match += 1

        a_score = float(a.get("score_100", 0.0) or 0.0)
        b_score = float(b.get("score_100", 0.0) or 0.0)
        deltas.append(abs(a_score - b_score))

    deltas.sort()
    idx = int(math.ceil(0.95 * len(deltas)) - 1) if deltas else 0
    if idx < 0:
        idx = 0
    p95 = deltas[idx] if deltas else 0.0

    total = float(len(paired))
    return {
        "samples": len(paired),
        "action_match_rate": round(action_match / total, 4),
        "path_match_rate": round(path_match / total, 4),
        "sector_match_rate": round(sector_match / total, 4),
        "score_delta_p95": round(p95, 4),
    }


def load_gate_policy() -> Dict[str, Any]:
    cfg = ConfigCenter()
    cfg.register("gate_policy", Path(__file__).resolve().parent.parent / "configs" / "gate_policy.yaml")
    return cfg.get_registered("gate_policy", {})


def evaluate_shadow_gate(metrics: Dict[str, float], gate_policy: Dict[str, Any]) -> Dict[str, Any]:
    shadow = gate_policy.get("shadow", {})
    failed: List[str] = []

    if float(metrics.get("samples", 0.0) or 0.0) < float(shadow.get("min_events_per_day", 30) or 30):
        failed.append("samples")
    if float(metrics.get("action_match_rate", 0.0) or 0.0) < float(shadow.get("action_match_rate_min", 0.95) or 0.95):
        failed.append("action_match_rate")
    if float(metrics.get("path_match_rate", 0.0) or 0.0) < float(shadow.get("path_match_rate_min", 0.90) or 0.90):
        failed.append("path_match_rate")
    if float(metrics.get("sector_match_rate", 0.0) or 0.0) < float(shadow.get("sector_match_rate_min", 0.90) or 0.90):
        failed.append("sector_match_rate")
    if float(metrics.get("score_delta_p95", 0.0) or 0.0) > float(shadow.get("score_delta_p95_max", 8.0) or 8.0):
        failed.append("score_delta_p95")

    reason_map = {
        "samples": "SHADOW_SAMPLE_INSUFFICIENT",
        "action_match_rate": "SHADOW_ACTION_MISMATCH",
        "path_match_rate": "SHADOW_PATH_MISMATCH",
        "sector_match_rate": "SHADOW_SECTOR_MISMATCH",
        "score_delta_p95": "SHADOW_SCORE_DELTA_EXCEEDED",
    }
    gate_reason_codes = [reason_map[item] for item in failed]

    return {
        "passed": len(failed) == 0,
        "failed_checks": failed,
        "gate_reason_codes": gate_reason_codes,
        "gate_reason_code": gate_reason_codes[0] if gate_reason_codes else "ALL_PASSED",
    }


def compare_and_gate(a_records: List[Dict[str, Any]], b_records: List[Dict[str, Any]], gate_policy: Dict[str, Any]) -> Dict[str, Any]:
    metrics = compare_shadow(a_records, b_records)
    gate = evaluate_shadow_gate(metrics, gate_policy)
    return {
        "metrics": metrics,
        "gate": gate,
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Compare A/B shadow outputs and evaluate shadow gate.")
    parser.add_argument("--a-jsonl", required=True, help="Path to A-track jsonl")
    parser.add_argument("--b-jsonl", required=True, help="Path to B-track jsonl")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(argv)

    a_path = Path(args.a_jsonl)
    b_path = Path(args.b_jsonl)
    if not a_path.exists() or not b_path.exists():
        print(json.dumps({"error": "input file not found"}, ensure_ascii=False))
        return 1

    a_records = _read_jsonl(a_path)
    b_records = _read_jsonl(b_path)
    gate_policy = load_gate_policy()
    result = compare_and_gate(a_records, b_records, gate_policy)

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))

    return 0 if bool((result.get("gate") or {}).get("passed", False)) else 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
