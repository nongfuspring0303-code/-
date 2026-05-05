from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
import tempfile

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
    assert policy["lifecycle"]["stale_event"]["allowed_reasons"]
    assert policy["fatigue"]["allowed_fatigue_bucket"]
    assert policy["fatigue"]["bucket_thresholds"]
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
    assert "stale_event" in out

    policy = _load_policy()
    assert out["lifecycle_state"] in policy["lifecycle"]["allowed_lifecycle_state"]
    assert out["time_scale"] in policy["lifecycle"]["allowed_time_scale"]
    assert out["decay_profile"] in policy["lifecycle"]["allowed_decay_profile"]
    assert out["stale_event"]["reason"] in policy["lifecycle"]["stale_event"]["allowed_reasons"]


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


def test_pr111_fatigue_bucket_thresholds_follow_config() -> None:
    custom_cfg = {
        "count_to_fatigue_score": {2: 0, 3: 20, 4: 40, 5: 60, 6: 80, 7: 100},
        "fatigue_discount_threshold": 70,
        "fatigue_discount_factor": 0.5,
        "watch_mode_threshold": 85,
        "dead_event_reset_days": 30,
        "take_profit_penalty_factor": 0.5,
        "fatigue": {
            "bucket_thresholds": {
                "critical_min": 95,
                "high_min": 85,
                "medium_min": 60,
                "low_min": 30,
            }
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "fatigue_custom.yaml"
        cfg_path.write_text(yaml.safe_dump(custom_cfg, sort_keys=False), encoding="utf-8")
        out = FatigueCalculator(config_path=str(cfg_path)).run(
            {
                "event_id": "ME-A-PR111-003",
                "category": "A",
                "lifecycle_state": "Active",
                "category_active_count": 4,  # fatigue_final=40
                "tag_active_counts": {},
                "days_since_last_dead": 0,
            }
        ).data
    assert out["fatigue_final"] == 40
    assert out["fatigue_bucket"] == "low"


def test_pr111_stale_event_downgrades_active_to_exhaustion() -> None:
    out = LifecycleManager().run(
        {
            "event_id": "ME-PR111-STALE-001",
            "category": "A",
            "severity": "E3",
            "source_rank": "A",
            "headline": "Policy signal fades without market follow-through",
            "detected_at": "2026-05-01T00:00:00Z",
            "previous_lifecycle_state": "Active",
            "elapsed_hours": 49,
            "market_validated": False,
            "has_material_update": False,
            "is_official_confirmed": True,
        }
    ).data

    assert out["lifecycle_state"] == "Exhaustion"
    assert out["stale_event"]["is_stale"] is True
    assert out["stale_event"]["downgrade_applied"] is True
    assert out["stale_event"]["downgrade_from"] == "Active"
    assert out["stale_event"]["downgrade_to"] == "Exhaustion"
    assert out["stale_event"]["reason"] == "stale_without_market_validation"


def test_pr111_stale_event_downgrades_continuation_to_exhaustion() -> None:
    out = LifecycleManager().run(
        {
            "event_id": "ME-PR111-STALE-002",
            "category": "A",
            "severity": "E3",
            "source_rank": "A",
            "headline": "Continuation phase stalls without updates",
            "detected_at": "2026-05-01T00:00:00Z",
            "previous_lifecycle_state": "Continuation",
            "elapsed_hours": 73,
            "market_validated": True,
            "has_material_update": False,
            "is_official_confirmed": True,
        }
    ).data
    assert out["stale_event"]["downgrade_applied"] is True
    assert out["stale_event"]["downgrade_from"] == "Continuation"
    assert out["stale_event"]["downgrade_to"] == "Exhaustion"
    assert out["stale_event"]["reason"] == "stale_without_material_update"
    assert out["lifecycle_state"] == out["stale_event"]["downgrade_to"]


def test_pr111_stale_event_downgrades_detected_to_dead() -> None:
    out = LifecycleManager().run(
        {
            "event_id": "ME-PR111-STALE-003",
            "category": "A",
            "severity": "E2",
            "source_rank": "C",
            "headline": "Rumor stays unconfirmed",
            "detected_at": "2026-05-01T00:00:00Z",
            "previous_lifecycle_state": "Detected",
            "elapsed_hours": 25,
            "market_validated": False,
            "has_material_update": False,
            "is_official_confirmed": False,
        }
    ).data
    assert out["stale_event"]["downgrade_applied"] is True
    assert out["stale_event"]["downgrade_from"] == "Detected"
    assert out["stale_event"]["downgrade_to"] == "Dead"
    assert out["stale_event"]["reason"] == "stale_without_confirmation"
    assert out["lifecycle_state"] == out["stale_event"]["downgrade_to"]


def test_pr111_stale_thresholds_follow_policy_config() -> None:
    custom_policy = {
        "schema_version": "stage6.lifecycle_fatigue_policy.v1",
        "version": "1.0.0",
        "lifecycle": {
            "allowed_lifecycle_state": ["Detected", "Verified", "Active", "Continuation", "Exhaustion", "Dead", "Archived"],
            "allowed_time_scale": ["intraday", "overnight", "multiweek", "none"],
            "allowed_decay_profile": ["fast", "medium", "slow", "exhausted", "none"],
            "time_scale_mapping": {"intraday": "intraday", "overnight": "overnight", "multiweek": "multiweek", "none": "none"},
            "decay_profile_mapping": {"first_impulse": "fast", "continuation": "slow", "exhaustion": "exhausted", "dead": "none"},
            "stale_event": {
                "active_without_market_validation_hours": 72,
                "continuation_without_material_update_hours": 72,
                "detected_without_confirmation_hours": 24,
                "downgrade_targets": {"Active": "Exhaustion", "Continuation": "Exhaustion", "Detected": "Dead"},
                "allowed_reasons": [
                    "not_stale",
                    "stale_without_market_validation",
                    "stale_without_material_update",
                    "stale_without_confirmation",
                    "contradicted_by_new_fact",
                    "manual_archive",
                ],
            },
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        policy_path = Path(tmpdir) / "lifecycle_policy.yaml"
        policy_path.write_text(yaml.safe_dump(custom_policy, sort_keys=False), encoding="utf-8")
        out = LifecycleManager(config_path=str(policy_path)).run(
            {
                "event_id": "ME-PR111-STALE-004",
                "category": "A",
                "severity": "E3",
                "source_rank": "A",
                "headline": "Policy signal fades without market follow-through",
                "detected_at": "2026-05-01T00:00:00Z",
                "previous_lifecycle_state": "Active",
                "elapsed_hours": 49,
                "market_validated": False,
                "has_material_update": False,
                "is_official_confirmed": True,
            }
        ).data
    assert out["stale_event"]["downgrade_applied"] is False
    assert out["stale_event"]["reason"] == "not_stale"


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
    assert "stale_event" in contract
