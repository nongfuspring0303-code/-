from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from execution_suggestion_builder import ExecutionSuggestionBuilder


def _load_policy() -> dict:
    return yaml.safe_load((ROOT / "configs" / "execution_suggestion_policy.yaml").read_text(encoding="utf-8"))


def _load_schema() -> dict:
    return json.loads((ROOT / "schemas" / "execution_suggestion.schema.json").read_text(encoding="utf-8"))


def test_execution_suggestion_policy_schema_versions_present() -> None:
    policy = _load_policy()
    assert policy.get("schema_version") == "stage6.execution_suggestion_policy.v1"
    assert policy.get("mode") == "advisory_only"
    assert policy.get("guardrails", {}).get("advisory_only") is True
    assert policy.get("guardrails", {}).get("allow_runtime_consumer") is False


def test_execution_suggestion_schema_enums_align_with_policy() -> None:
    policy = _load_policy()
    schema = _load_schema()
    allowed = policy["allowed_values"]

    assert schema["properties"]["trade_type"]["enum"] == allowed["trade_type"]
    assert schema["properties"]["risk_switch"]["enum"] == allowed["risk_switch"]
    assert schema["properties"]["overnight_allowed"]["enum"] == allowed["overnight_allowed"]
    assert schema["properties"]["entry_timing"]["properties"]["window"]["enum"] == allowed["entry_timing_window"]
    assert schema["properties"]["stop_condition"]["properties"]["kind"]["enum"] == allowed["stop_condition_kind"]


def test_execution_suggestion_threshold_changes_affect_runtime_behavior(tmp_path: Path) -> None:
    policy = _load_policy()
    policy["thresholds"]["breakout_min_score"] = 95
    policy["thresholds"]["low_buy_min_score"] = 70
    policy_path = tmp_path / "execution_suggestion_policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding="utf-8")

    builder = ExecutionSuggestionBuilder(config_path=str(policy_path))
    out = builder.run(
        {
            "score": 85,
            "fatigue_score": 30,
            "has_opportunity": True,
            "market_validated": True,
            "lifecycle_state": "Active",
            "stale_event": {"is_stale": False},
        }
    )
    assert out.status.value == "success"
    # With breakout threshold raised to 95, score=85 should no longer be breakout.
    assert out.data["trade_type"] == "low_buy"


def test_execution_suggestion_policy_missing_file_fails_fast(tmp_path: Path) -> None:
    missing = tmp_path / "missing_policy.yaml"
    with pytest.raises(FileNotFoundError):
        ExecutionSuggestionBuilder(config_path=str(missing))


def test_execution_suggestion_policy_invalid_threshold_value_fails(tmp_path: Path) -> None:
    policy = _load_policy()
    policy["thresholds"]["breakout_min_score"] = "bad-number"
    policy_path = tmp_path / "bad_threshold_policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError):
        ExecutionSuggestionBuilder(config_path=str(policy_path))


def test_execution_suggestion_policy_invalid_band_value_fails(tmp_path: Path) -> None:
    policy = _load_policy()
    policy["position_bands"]["breakout"]["min"] = 0.8
    policy["position_bands"]["breakout"]["max"] = 0.2
    policy_path = tmp_path / "bad_band_policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError):
        ExecutionSuggestionBuilder(config_path=str(policy_path))
