from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from execution_suggestion_builder import ExecutionSuggestionBuilder
from full_workflow_runner import FullWorkflowRunner


def _load_schema() -> dict:
    return json.loads((ROOT / "schemas" / "execution_suggestion.schema.json").read_text(encoding="utf-8"))


def test_execution_suggestion_schema_validates_builder_output() -> None:
    schema = _load_schema()
    out = ExecutionSuggestionBuilder().run(
        {
            "score": 86,
            "fatigue_score": 40,
            "has_opportunity": True,
            "market_validated": True,
            "lifecycle_state": "Active",
            "stale_event": {"is_stale": False},
        }
    )
    assert out.status.value == "success"
    jsonschema.validate(out.data, schema)
    assert set(out.data.keys()) == {
        "trade_type",
        "position_sizing",
        "entry_timing",
        "risk_switch",
        "stop_condition",
        "overnight_allowed",
    }


def test_execution_suggestion_schema_rejects_invalid_enum_value() -> None:
    schema = _load_schema()
    bad = {
        "trade_type": "invalid_trade_type",
        "position_sizing": {"mode": "range", "suggested_pct_min": 0.1, "suggested_pct_max": 0.2, "note": "x"},
        "entry_timing": {"window": "breakout_confirm", "trigger": "x"},
        "risk_switch": "normal",
        "stop_condition": {"kind": "price_stop", "rule": "x"},
        "overnight_allowed": "false",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_full_workflow_emits_execution_suggestion_contract() -> None:
    schema = _load_schema()
    payload = {
        "headline": "Fed announces emergency liquidity action after tariff shock",
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
    out = FullWorkflowRunner().run(payload)
    suggestion = out["analysis"]["execution_suggestion"]
    jsonschema.validate(suggestion, schema)


def test_execution_suggestion_score_boundary_breakout_at_80() -> None:
    out = ExecutionSuggestionBuilder().run(
        {
            "score": 80,
            "fatigue_score": 40,
            "has_opportunity": True,
            "market_validated": True,
            "lifecycle_state": "Active",
            "stale_event": {"is_stale": False},
        }
    )
    assert out.status.value == "success"
    assert out.data["trade_type"] == "breakout"


def test_execution_suggestion_missing_score_fails() -> None:
    out = ExecutionSuggestionBuilder().run(
        {
            "fatigue_score": 40,
            "has_opportunity": True,
            "market_validated": True,
            "lifecycle_state": "Active",
            "stale_event": {"is_stale": False},
        }
    )
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_SCORE"


def test_execution_suggestion_missing_fatigue_score_fails() -> None:
    out = ExecutionSuggestionBuilder().run(
        {
            "score": 75,
            "has_opportunity": True,
            "market_validated": True,
            "lifecycle_state": "Active",
            "stale_event": {"is_stale": False},
        }
    )
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_FATIGUE_SCORE"


def test_execution_suggestion_intraday_only_path_reachable() -> None:
    out = ExecutionSuggestionBuilder().run(
        {
            "score": 70,
            "fatigue_score": 30,
            "has_opportunity": True,
            "market_validated": False,
            "lifecycle_state": "Verified",
            "stale_event": {"is_stale": False},
        }
    )
    assert out.status.value == "success"
    assert out.data["trade_type"] == "intraday_only"
