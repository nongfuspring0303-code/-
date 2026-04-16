import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from verify_theme_replay import build_idempotency_key, verify_replay_consistency


def test_idempotency_key_uses_only_required_fields():
    assert build_idempotency_key("evt-1", "v1", "T0") == "evt-1|v1|T0"


def test_replay_consistency_detects_key_collision_with_different_output():
    records = [
        {
            "event_id": "evt-1",
            "config_version": "v1",
            "evaluation_window": "T0",
            "input_snapshot": {"headline": "A"},
            "output_snapshot": {
                "contract_name": "theme_catalyst_engine",
                "contract_version": "v1.0",
                "producer_module": "theme_engine",
                "safe_to_consume": False,
                "error_code": "CONFIG_MISSING",
                "fallback_reason": "CONFIG_MISSING",
                "degraded_mode": True,
                "trade_grade": "B",
                "conflict_flag": False,
            },
        },
        {
            "event_id": "evt-1",
            "config_version": "v1",
            "evaluation_window": "T0",
            "input_snapshot": {"headline": "A"},
            "output_snapshot": {
                "contract_name": "theme_catalyst_engine",
                "contract_version": "v1.0",
                "producer_module": "theme_engine",
                "safe_to_consume": False,
                "error_code": "CONFIG_MISSING",
                "fallback_reason": "CONFIG_MISSING",
                "degraded_mode": True,
                "trade_grade": "C",
                "conflict_flag": False,
            },
        },
    ]

    report = verify_replay_consistency(records)

    assert report["replay_consistency"] is False
    assert report["inconsistent_keys"] == ["evt-1|v1|T0"]
