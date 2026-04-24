#!/usr/bin/env python3
"""Build deterministic clean-window metrics for PR91 A-side DoD items."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner


def _payload(request_id: str, *, has_opportunity: bool, opportunity_count: int, default_used: bool) -> Dict[str, Any]:
    return {
        "request_id": request_id,
        "A0": 30,
        "A-1": 70,
        "A1": 88,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 20,
        "event_state": "Developing",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
        "symbol": "SPY",
        "has_opportunity": has_opportunity,
        "opportunity_count": opportunity_count,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": default_used,
        "market_data_fallback_used": False,
        "tradeable": True,
        "a1_market_validation": "pass",
        "macro_confirmation": "supportive",
        "sector_confirmation": "strong",
        "leader_confirmation": "confirmed",
        "event_type": "tech",
        "event_time": "2026-04-24T00:00:00Z",
        "event_name": "stage5_a_clean_window",
        "evidence_grade": "A",
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _metric_missing_opportunity_but_execute(row: Dict[str, Any]) -> bool:
    if str(row.get("final_action", "")) != "EXECUTE":
        return False
    count = row.get("opportunity_count")
    return count in (None, 0, False)


def _metric_market_data_default_used_in_execute(row: Dict[str, Any]) -> bool:
    if str(row.get("final_action", "")) != "EXECUTE":
        return False
    output_gate = row.get("output_gate", {}) if isinstance(row.get("output_gate"), dict) else {}
    blockers = [str(x).lower() for x in (output_gate.get("blockers") or [])]
    reason = str(row.get("final_reason", "")).lower()
    return "market_data_default_used" in blockers or "market_data_default_used" in reason


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PR91 A-side clean-window metrics.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/stage5/artifacts/pr91_a_clean_window_metrics.json"),
        help="Output JSON metrics path.",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=Path("docs/stage5/artifacts/pr91_a_clean_window_logs"),
        help="Deterministic clean-window log directory.",
    )
    args = parser.parse_args()

    out_path = (ROOT / args.out).resolve()
    logs_dir = (ROOT / args.logs_dir).resolve()
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    runner = WorkflowRunner(
        request_store_path=str(logs_dir / "seen_ids.txt"),
        audit_dir=str(logs_dir),
    )

    payloads = [
        _payload("PR91-A-CLEAN-001", has_opportunity=True, opportunity_count=1, default_used=False),
        _payload("PR91-A-CLEAN-002", has_opportunity=True, opportunity_count=1, default_used=False),
        _payload("PR91-A-CLEAN-003", has_opportunity=True, opportunity_count=1, default_used=False),
        _payload("PR91-A-CLEAN-004", has_opportunity=True, opportunity_count=1, default_used=False),
        # Negative controls: should not execute.
        _payload("PR91-A-CLEAN-005", has_opportunity=False, opportunity_count=0, default_used=False),
        _payload("PR91-A-CLEAN-006", has_opportunity=True, opportunity_count=1, default_used=True),
    ]

    for item in payloads:
        runner.run(item)

    decision_rows = _read_jsonl(logs_dir / "decision_gate.jsonl")
    execute_rows = [row for row in decision_rows if str(row.get("final_action", "")) == "EXECUTE"]

    missing_opportunity_but_execute_count = sum(1 for row in decision_rows if _metric_missing_opportunity_but_execute(row))
    market_data_default_used_in_execute_count = sum(
        1 for row in decision_rows if _metric_market_data_default_used_in_execute(row)
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "PR91 Stage5 Final Acceptance - A-side clean-window DoD metrics",
        "log_window": str(logs_dir.relative_to(ROOT)),
        "sample_size": {
            "decision_gate_rows": len(decision_rows),
            "execute_rows": len(execute_rows),
        },
        "metrics": {
            "missing_opportunity_but_execute_count": missing_opportunity_but_execute_count,
            "market_data_default_used_in_execute_count": market_data_default_used_in_execute_count,
        },
        "targets": {
            "missing_opportunity_but_execute_count": 0,
            "market_data_default_used_in_execute_count": 0,
        },
        "status": {
            "missing_opportunity_but_execute_count": "PASS"
            if missing_opportunity_but_execute_count == 0
            else "FAIL",
            "market_data_default_used_in_execute_count": "PASS"
            if market_data_default_used_in_execute_count == 0
            else "FAIL",
        },
        "command": (
            "python3 scripts/build_pr91_a_clean_window_metrics.py "
            "--out docs/stage5/artifacts/pr91_a_clean_window_metrics.json "
            "--logs-dir docs/stage5/artifacts/pr91_a_clean_window_logs"
        ),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
