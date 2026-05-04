from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fatigue_calculator import FatigueCalculator
from full_workflow_runner import FullWorkflowRunner
from lifecycle_manager import LifecycleManager


def _load_policy() -> dict:
    return yaml.safe_load(
        (ROOT / "configs" / "lifecycle_fatigue_contract_policy.yaml").read_text(encoding="utf-8")
    )


def _load_schema() -> dict:
    return yaml.safe_load(
        (ROOT / "schemas" / "lifecycle_fatigue_contract.schema.json").read_text(encoding="utf-8")
    )


def test_pr111_policy_contract_exists() -> None:
    policy = _load_policy()
    assert policy["schema_version"] == "stage6.lifecycle_fatigue_policy.v1"
    assert policy["lifecycle"]["allowed_lifecycle_state"]
    assert policy["lifecycle"]["allowed_time_scale"]
    assert policy["lifecycle"]["allowed_decay_profile"]
    assert policy["fatigue"]["allowed_fatigue_bucket"]
    assert policy["fatigue"]["score_range"]["min"] == 0
    assert policy["fatigue"]["score_range"]["max"] == 100


def test_lifecycle_manager_exposes_pr111_atomic_fields() -> None:
    out = LifecycleManager().run(
        {
            "event_id": "ME-A-PR111-001",
            "category": "A",
            "severity": "E3",
            "source_rank": "A",
            "headline": "Policy pivot drives sector repricing",
            "detected_at": "2026-05-01T00:00:00Z",
            "is_official_confirmed": True,
            "market_validated": True,
            "has_material_update": True,
            "elapsed_hours": 4,
        }
    ).data
    assert "lifecycle_state" in out
    assert "time_scale" in out
    assert "decay_profile" in out

    policy = _load_policy()
    assert out["lifecycle_state"] in policy["lifecycle"]["allowed_lifecycle_state"]
    assert out["time_scale"] in policy["lifecycle"]["allowed_time_scale"]
    assert out["decay_profile"] in policy["lifecycle"]["allowed_decay_profile"]


def test_fatigue_calculator_exposes_pr111_atomic_fields() -> None:
    out = FatigueCalculator().run(
        {
            "event_id": "ME-A-PR111-002",
            "category": "A",
            "lifecycle_state": "Active",
            "category_active_count": 6,
            "tag_active_counts": {"policy_pivot": 7},
            "days_since_last_dead": 3,
        }
    ).data
    assert out["fatigue_score"] == out["fatigue_final"]
    assert out["fatigue_bucket"] in _load_policy()["fatigue"]["allowed_fatigue_bucket"]


def test_full_workflow_emits_lifecycle_fatigue_contract_and_validates_schema(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    state_db = tmp_path / "state.db"
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
    out = FullWorkflowRunner(audit_dir=str(logs_dir), state_db_path=str(state_db)).run(payload)
    contract = out["analysis"]["lifecycle_fatigue_contract"]
    jsonschema.validate(instance=contract, schema=_load_schema())

