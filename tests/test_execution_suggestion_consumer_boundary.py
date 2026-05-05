from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner
from workflow_runner import WorkflowRunner


def _workflow_payload() -> dict:
    return {
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
        "has_opportunity": True,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }


def test_workflow_runner_does_not_consume_execution_suggestion_field() -> None:
    runner = WorkflowRunner()
    base = _workflow_payload()
    out_base = runner.run(dict(base))

    injected = dict(base)
    injected["execution_suggestion"] = {
        "trade_type": "avoid",
        "position_sizing": {"mode": "zero", "suggested_pct_min": 0.0, "suggested_pct_max": 0.0, "note": "force"},
        "entry_timing": {"window": "none", "trigger": "force"},
        "risk_switch": "kill_switch",
        "stop_condition": {"kind": "event_stop", "rule": "force"},
        "overnight_allowed": "false",
    }
    out_injected = runner.run(injected)

    assert out_base["final"]["action"] == out_injected["final"]["action"]


def test_full_workflow_emits_suggestion_but_execution_output_has_no_suggestion() -> None:
    payload = {
        "headline": "Fed announces emergency liquidity action after tariff shock",
        "source": "https://www.reuters.com/markets/us/example",
        "timestamp": "2026-05-06T00:00:00Z",
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
    out = FullWorkflowRunner().run(payload)
    assert "execution_suggestion" in out["analysis"]
    assert "execution_suggestion" not in out["execution"]

