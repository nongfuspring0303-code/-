from __future__ import annotations

from pathlib import Path

from test_advisory_governance import _runner, assert_advisory_subsurface_boundary


def test_lifecycle_fatigue_stale_event_downgrades_without_mutating_final_output(tmp_path: Path) -> None:
    lifecycle_data = {
        "lifecycle_state": "Active",
        "internal_state": "ACTIVE_TRACK",
        "catalyst_state": "Active",
        "stale_event": {"is_stale": True},
    }
    out = _runner(tmp_path, lifecycle_data=lifecycle_data).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["advisory_governance"]

    assert surface["overall_status"] == "downgrade"
    assert "lifecycle_fatigue" in surface["active_governance_domains"]
    assert "stale_event" in surface["downgrade_reasons"]
    assert surface["lifecycle_fatigue_governance"]["downgrade"] is True
    assert surface["lifecycle_fatigue_governance"]["downgrade_reason"]
    assert_advisory_subsurface_boundary(
        out["analysis"]["lifecycle_fatigue_governance"],
        "lifecycle_fatigue_governance",
    )
    assert_advisory_subsurface_boundary(
        out["analysis"]["lifecycle_fatigue_governance"],
        "lifecycle_fatigue_governance",
    )
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_lifecycle_fatigue_over_fatigued_downgrades_without_final_mutation(tmp_path: Path) -> None:
    fatigue_data = {
        "fatigue_final": 90,
        "fatigue_score": 90,
        "fatigue_bucket": "high",
        "watch_mode": True,
        "a_minus_1_discount_factor": 0.5,
    }
    out = _runner(tmp_path, fatigue_data=fatigue_data).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["advisory_governance"]

    assert surface["overall_status"] == "downgrade"
    assert "lifecycle_fatigue" in surface["active_governance_domains"]
    assert "over_fatigued" in surface["downgrade_reasons"]
    assert surface["lifecycle_fatigue_governance"]["downgrade"] is True
    assert surface["lifecycle_fatigue_governance"]["downgrade_reason"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"
