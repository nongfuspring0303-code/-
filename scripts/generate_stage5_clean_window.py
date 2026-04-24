#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from full_workflow_runner import FullWorkflowRunner


ROOT = Path(__file__).resolve().parents[1]


def _payload(request_id: str, headline: str, **overrides: Any) -> Dict[str, Any]:
    base = {
        "request_id": request_id,
        "batch_id": "BATCH-STAGE5-CLEAN",
        "headline": headline,
        "source": "https://www.reuters.com/markets/us/example",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 24,
        "vix_change_pct": 20,
        "spx_move_pct": 1.8,
        "sector_move_pct": 3.0,
        "sequence": 1,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
    }
    base.update(overrides)
    return base


def generate_clean_window(logs_dir: Path) -> Dict[str, Any]:
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    state_db = logs_dir / "stage5_clean_state.db"
    runner = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(state_db))

    scenarios: List[Dict[str, Any]] = [
        _payload("REQ-STAGE5-CLEAN-001", "Fed announces emergency liquidity action after tariff shock"),
        _payload("REQ-STAGE5-CLEAN-002", "ECB signals policy pause while inflation cools", spx_move_pct=0.1, sector_move_pct=0.1),
        _payload(
            "REQ-STAGE5-CLEAN-003",
            "Major chipmaker guides above expectations on AI demand",
            market_data_source="default",
            market_data_default_used=True,
            market_data_stale=True,
            spx_move_pct=0.0,
            sector_move_pct=0.0,
        ),
        _payload("REQ-STAGE5-CLEAN-004", "Oil supply shock eases as inventories recover"),
    ]

    finals: List[Dict[str, str]] = []
    for payload in scenarios:
        out = runner.run(payload)
        final = out.get("execution", {}).get("final", {})
        finals.append(
            {
                "request_id": payload["request_id"],
                "action": str(final.get("action", "")),
                "reason": str(final.get("reason", "")),
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "logs_dir": str(logs_dir),
        "scenario_count": len(scenarios),
        "finals": finals,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Stage5 clean-window logs for final acceptance metrics")
    parser.add_argument("--logs-dir", type=Path, default=ROOT / "logs" / "stage5_acceptance_window")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "stage5" / "artifacts" / "pr91_stage5_clean_window_run.json")
    args = parser.parse_args()

    report = generate_clean_window(logs_dir=args.logs_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
