#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), check=False, text=True, capture_output=True)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_final_stock_usefulness(opportunity_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    for row in opportunity_rows:
        if str(row.get("action_after_gate", "")).upper() != "EXECUTE":
            continue
        if row.get("data_quality") != "valid":
            continue
        if "resolved" not in str(row.get("outcome_status", "")):
            continue
        if not str(row.get("symbol", "")).strip():
            continue
        alpha = _safe_float(row.get("sector_relative_alpha_t5"))
        t5 = _safe_float(row.get("t5_return"))
        bm = _safe_float(row.get("benchmark_return_t5"))
        if alpha is None or t5 is None or bm is None:
            continue
        candidates.append(row)

    useful = 0
    for row in candidates:
        alpha = float(row["sector_relative_alpha_t5"])
        t5 = float(row["t5_return"])
        bm = float(row["benchmark_return_t5"])
        label = str(row.get("outcome_label", "")).lower()
        # Unified "final usefulness":
        # correct directional outcome + positive sector-relative alpha + beat benchmark.
        if label == "hit" and alpha > 0 and t5 > bm:
            useful += 1

    return {
        "denominator_execute_valid_resolved_with_returns": len(candidates),
        "numerator_useful": useful,
        "final_stock_usefulness_rate": round(useful / len(candidates), 4) if candidates else None,
    }


def _pick_python_bin(python_bin: str) -> str:
    if python_bin.strip():
        return python_bin.strip()
    fallback = Path("/usr/bin/python3")
    if fallback.exists():
        return str(fallback)
    return sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description="Build unified mapping+outcome quality report")
    parser.add_argument("--logs-dir", type=Path, default=ROOT / "logs")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports" / "unified_quality")
    parser.add_argument("--python-bin", type=str, default="/usr/bin/python3")
    parser.add_argument(
        "--mapping-policy",
        type=Path,
        default=ROOT / "configs" / "ai_mapping_regression_policy.yaml",
    )
    parser.add_argument(
        "--mapping-prev-scorecard",
        type=Path,
        default=ROOT / "reports" / "ai_mapping_regression_eval" / "trace_scorecard_vnew_round6_rerun_with_buckets.jsonl",
    )
    parser.add_argument(
        "--mapping-new-scorecard",
        type=Path,
        default=ROOT / "logs" / "trace_scorecard.jsonl",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    outcome_dir = out_dir / "outcome"
    outcome_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _now_utc()
    py = _pick_python_bin(args.python_bin)

    run_records: Dict[str, Dict[str, Any]] = {}

    # 1) Stage5 acceptance metrics (existing script)
    stage5_json = out_dir / "stage5_acceptance_metrics.json"
    cmd_stage5 = [
        py,
        str(ROOT / "scripts" / "compute_stage5_acceptance_metrics.py"),
        "--logs-dir",
        str(args.logs_dir),
        "--out",
        str(stage5_json),
    ]
    p_stage5 = _run(cmd_stage5, ROOT)
    run_records["stage5_acceptance"] = {
        "cmd": cmd_stage5,
        "returncode": p_stage5.returncode,
        "stderr_tail": p_stage5.stderr[-1000:],
    }

    # 2) Outcome attribution (existing script)
    cmd_outcome = [
        py,
        str(ROOT / "scripts" / "outcome_attribution_engine.py"),
        "--logs-dir",
        str(args.logs_dir),
        "--out-dir",
        str(outcome_dir),
        "--horizon",
        "t5",
        "--emit-report",
    ]
    p_outcome = _run(cmd_outcome, ROOT)
    run_records["outcome_attribution"] = {
        "cmd": cmd_outcome,
        "returncode": p_outcome.returncode,
        "stderr_tail": p_outcome.stderr[-1000:],
    }

    # 3) Mapping regression eval (existing script, optional when input missing)
    mapping_json = out_dir / "mapping_eval.json"
    mapping_md = out_dir / "mapping_eval.md"
    mapping_executed = False
    if args.mapping_prev_scorecard.exists() and args.mapping_new_scorecard.exists() and args.mapping_policy.exists():
        mapping_executed = True
        cmd_mapping = [
            py,
            str(ROOT / "scripts" / "run_ai_mapping_regression_eval.py"),
            "--policy",
            str(args.mapping_policy),
            "--prev-scorecard",
            str(args.mapping_prev_scorecard),
            "--new-scorecard",
            str(args.mapping_new_scorecard),
            "--out-json",
            str(mapping_json),
            "--out-md",
            str(mapping_md),
        ]
        p_mapping = _run(cmd_mapping, ROOT)
        run_records["mapping_regression"] = {
            "cmd": cmd_mapping,
            "returncode": p_mapping.returncode,
            "stderr_tail": p_mapping.stderr[-1000:],
        }
    else:
        run_records["mapping_regression"] = {
            "skipped": True,
            "reason": "mapping prev/new scorecard or policy file missing",
        }

    stage5_payload = _load_json(stage5_json)
    outcome_summary = _load_json(outcome_dir / "outcome_summary.json")
    opportunity_rows = _load_jsonl(outcome_dir / "opportunity_outcome.jsonl")
    mapping_payload = _load_json(mapping_json) if mapping_executed else {}

    stage5_metrics = stage5_payload.get("metrics", {})
    mapping_overall = (((mapping_payload.get("v_new") or {}).get("groups") or {}).get("overall") or {})
    summary = outcome_summary.get("summary", outcome_summary)

    final_usefulness = _compute_final_stock_usefulness(opportunity_rows)

    unified = {
        "generated_at_utc": generated_at,
        "inputs": {
            "logs_dir": str(args.logs_dir),
            "mapping_policy": str(args.mapping_policy),
            "mapping_prev_scorecard": str(args.mapping_prev_scorecard),
            "mapping_new_scorecard": str(args.mapping_new_scorecard),
        },
        "run_status": run_records,
        "core_metrics": {
            "mapping": {
                "conduction_mapping_accuracy": mapping_overall.get("conduction_mapping_accuracy"),
                "sector_recall": mapping_overall.get("sector_recall"),
                "ticker_hit_rate": mapping_overall.get("ticker_hit_rate"),
                "ticker_false_positive_rate": mapping_overall.get("ticker_false_positive_rate"),
                "empty_mapping_rate": mapping_overall.get("empty_mapping_rate"),
            },
            "outcome": {
                "hit_rate_t5": summary.get("hit_rate_t5"),
                "avg_alpha_t5": summary.get("avg_alpha_t5"),
                "avg_return_t5": summary.get("avg_return_t5"),
                "missed_opportunity_rate": summary.get("missed_opportunity_rate"),
                "overblock_rate": summary.get("overblock_rate"),
            },
            "pipeline_health": {
                "trace_join_success_rate": stage5_metrics.get("trace_join_success_rate"),
                "missing_opportunity_but_execute_count": stage5_metrics.get("missing_opportunity_but_execute_count"),
                "market_data_default_used_in_execute_count": stage5_metrics.get("market_data_default_used_in_execute_count"),
                "p95_decision_latency": stage5_metrics.get("p95_decision_latency"),
            },
            "final_usefulness": final_usefulness,
        },
    }

    out_json = out_dir / "unified_quality_report.json"
    out_json.write_text(json.dumps(unified, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Unified Quality Report",
        "",
        f"- generated_at_utc: `{generated_at}`",
        f"- logs_dir: `{args.logs_dir}`",
        "",
        "## Core Metrics",
        "",
        "### Mapping",
        f"- conduction_mapping_accuracy: `{mapping_overall.get('conduction_mapping_accuracy')}`",
        f"- sector_recall: `{mapping_overall.get('sector_recall')}`",
        f"- ticker_hit_rate: `{mapping_overall.get('ticker_hit_rate')}`",
        f"- ticker_false_positive_rate: `{mapping_overall.get('ticker_false_positive_rate')}`",
        f"- empty_mapping_rate: `{mapping_overall.get('empty_mapping_rate')}`",
        "",
        "### Outcome (T+5)",
        f"- hit_rate_t5: `{summary.get('hit_rate_t5')}`",
        f"- avg_alpha_t5: `{summary.get('avg_alpha_t5')}`",
        f"- avg_return_t5: `{summary.get('avg_return_t5')}`",
        f"- missed_opportunity_rate: `{summary.get('missed_opportunity_rate')}`",
        f"- overblock_rate: `{summary.get('overblock_rate')}`",
        "",
        "### Pipeline Health",
        f"- trace_join_success_rate: `{stage5_metrics.get('trace_join_success_rate')}`",
        f"- missing_opportunity_but_execute_count: `{stage5_metrics.get('missing_opportunity_but_execute_count')}`",
        f"- market_data_default_used_in_execute_count: `{stage5_metrics.get('market_data_default_used_in_execute_count')}`",
        f"- p95_decision_latency: `{stage5_metrics.get('p95_decision_latency')}`",
        "",
        "### Final Stock Usefulness (supplement)",
        f"- denominator_execute_valid_resolved_with_returns: `{final_usefulness.get('denominator_execute_valid_resolved_with_returns')}`",
        f"- numerator_useful: `{final_usefulness.get('numerator_useful')}`",
        f"- final_stock_usefulness_rate: `{final_usefulness.get('final_stock_usefulness_rate')}`",
        "",
        "## Script Run Status",
        f"- stage5_acceptance.returncode: `{run_records.get('stage5_acceptance', {}).get('returncode')}`",
        f"- outcome_attribution.returncode: `{run_records.get('outcome_attribution', {}).get('returncode')}`",
        f"- mapping_regression: `{run_records.get('mapping_regression', {}).get('returncode', 'skipped')}`",
    ]
    (out_dir / "unified_quality_report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"OK: wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
