#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from workflow_runner import WorkflowRunner


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "edt_goldens" / "member_b_stage4_consumption_cases.json"


def _load_fixture_cases() -> List[Dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [case for case in payload.get("cases", []) if not case.get("reference_only")]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _contains_market_flag(record: Dict[str, Any], token: str) -> bool:
    if token in str(record.get("final_reason", "")):
        return True
    output_gate = record.get("output_gate") or {}
    if token in str(output_gate.get("reason", "")):
        return True
    return token in json.dumps(record, ensure_ascii=False)


def _window_bounds(records: List[Dict[str, Any]]) -> Tuple[str, str]:
    stamps = sorted(str(r.get("logged_at", "")) for r in records if str(r.get("logged_at", "")))
    if not stamps:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return now, now
    return stamps[0], stamps[-1]


def _generate_runtime_logs(rounds: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    cases = _load_fixture_cases()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        logs_dir = tmp_root / "logs"
        runner = WorkflowRunner(
            audit_dir=str(logs_dir),
            request_store_path=str(tmp_root / "seen_request_ids.txt"),
        )

        total_runs = 0
        for round_idx in range(rounds):
            for case_idx, case in enumerate(cases):
                payload = dict(case["payload"])
                payload["request_id"] = f"PR88-S4-{round_idx:02d}-{case_idx:03d}"
                payload["batch_id"] = f"PR88-BATCH-{round_idx:02d}"
                runner.run(payload)
                total_runs += 1

        decision_rows = _read_jsonl(logs_dir / "decision_gate.jsonl")
        replay_rows = _read_jsonl(logs_dir / "replay_write.jsonl")
        execution_rows = _read_jsonl(logs_dir / "execution_emit.jsonl")

        return (
            decision_rows,
            replay_rows,
            execution_rows,
            {"total_runs": total_runs, "fixture_cases": len(cases), "rounds": rounds},
        )


def collect_metrics(rounds: int) -> Dict[str, Any]:
    decision_rows, replay_rows, execution_rows, generation_meta = _generate_runtime_logs(rounds)

    decision_count = len(decision_rows)
    fallback_count = sum(1 for row in decision_rows if _contains_market_flag(row, "market_data_fallback_used"))
    default_count = sum(1 for row in decision_rows if _contains_market_flag(row, "market_data_default_used"))
    manual_review_count = sum(
        1
        for row in decision_rows
        if str(row.get("final_action", "")).upper() in {"WATCH", "PENDING_CONFIRM", "BLOCK", "FORCE_CLOSE"}
    )
    execute_count = sum(1 for row in decision_rows if str(row.get("final_action", "")).upper() == "EXECUTE")

    window_start, window_end = _window_bounds(decision_rows)
    replay_request_ids = {str(r.get("request_id", "")) for r in replay_rows if str(r.get("request_id", ""))}
    execution_request_ids = {str(r.get("request_id", "")) for r in execution_rows if str(r.get("request_id", ""))}

    return {
        "window_name": "pr88_stage4_runtime_window",
        "window_start_utc": window_start,
        "window_end_utc": window_end,
        "source": {
            "mode": "generated_runtime_window_from_fixture_payloads",
            "fixture_path": str(FIXTURE_PATH.relative_to(ROOT)),
            "logs_dir": "transient_tempdir_runtime_logs",
            **generation_meta,
        },
        "counts": {
            "decision_gate_rows": decision_count,
            "replay_write_rows": len(replay_rows),
            "execution_emit_rows": len(execution_rows),
            "execute_rows": execute_count,
            "manual_review_rows": manual_review_count,
        },
        "ratios": {
            "fallback_used_ratio": (fallback_count / decision_count) if decision_count else 0.0,
            "default_used_ratio": (default_count / decision_count) if decision_count else 0.0,
            "manual_review_ratio": (manual_review_count / decision_count) if decision_count else 0.0,
            "execution_emit_per_decision_ratio": (len(execution_rows) / decision_count) if decision_count else 0.0,
        },
        "replay_execution_alignment": {
            "execution_ids_missing_in_replay": sorted(execution_request_ids - replay_request_ids),
            "replay_ids_without_execution": sorted(replay_request_ids - execution_request_ids),
            "alignment_ok": len(execution_request_ids - replay_request_ids) == 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Stage4 runtime-window metrics from decision/replay/execution logs.")
    parser.add_argument("--rounds", type=int, default=5, help="How many passes over fixture payloads to generate the window.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/stage5/artifacts/pr88_stage4_runtime_window_metrics.json"),
    )
    args = parser.parse_args()

    report = collect_metrics(rounds=max(1, args.rounds))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
