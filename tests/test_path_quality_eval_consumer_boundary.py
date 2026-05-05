from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

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


def test_workflow_runner_does_not_consume_path_quality_eval() -> None:
    """Injecting path_quality_eval into WorkflowRunner payload must not change final.action."""
    runner = WorkflowRunner()
    base = _workflow_payload()
    out_base = runner.run(dict(base))

    injected = dict(base)
    injected["path_quality_eval"] = {
        "path_accuracy": 0.99,
        "validation_accuracy": 0.99,
        "direction_relative_accuracy": 0.99,
        "direction_absolute_accuracy": 0.99,
        "dominant_driver_accuracy": 0.99,
        "expectation_gap_accuracy": 0.99,
        "execution_decision_quality": 0.99,
        "composite_score": 0.99,
        "grade": "Excellent",
    }
    out_injected = runner.run(injected)

    assert out_base["final"]["action"] == out_injected["final"]["action"]
