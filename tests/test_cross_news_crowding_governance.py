from __future__ import annotations

from pathlib import Path

from test_advisory_governance import _runner, assert_advisory_subsurface_boundary


def test_cross_news_unresolved_conflict_forces_manual_review_without_final_mutation(tmp_path: Path) -> None:
    payload = {
        "headline": "QCOM jumps",
        "cross_news_conflicts": [
            {
                "symbol": "QCOM",
                "theme": "semiconductor",
                "status": "unresolved",
                "reason": "opposite_direction_news",
                "direction_a": "positive",
                "direction_b": "negative",
                "source_a": "source_a",
                "source_b": "source_b",
                "evidence": "same symbol opposite direction",
            }
        ],
    }
    out = _runner(tmp_path, enable_crowding_guard=False).run(payload)
    surface = out["analysis"]["advisory_governance"]
    cross = out["analysis"]["cross_news_governance"]

    assert surface["overall_status"] == "manual_review"
    assert surface["requires_human_review"] is True
    assert "cross_news" in surface["active_governance_domains"]
    assert cross["conflict_status"] == "conflict_detected"
    assert cross["conflict_reason"]
    assert cross["conflict_evidence"]
    assert cross["conflict_evidence"][0]["symbol"] == "QCOM"
    assert cross["conflict_evidence"][0]["theme"] == "semiconductor"
    assert cross["conflict_evidence"][0]["reason"]
    assert cross["requires_human_review"] is True
    assert_advisory_subsurface_boundary(cross, "cross_news_governance")
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_crowding_signal_downgrades_without_creating_final_candidate(tmp_path: Path) -> None:
    payload = {
        "headline": "QCOM jumps",
        "crowding_signals": [
            {
                "symbol": "QCOM",
                "theme": "semiconductor",
                "crowded": True,
                "evidence": "theme_overcrowded",
                "candidate_count": 12,
                "threshold": 8,
            }
        ],
    }
    out = _runner(tmp_path, enable_cross_news_guard=False).run(payload)
    surface = out["analysis"]["advisory_governance"]
    crowding = out["analysis"]["crowding_governance"]

    assert surface["overall_status"] == "downgrade"
    assert "crowding" in surface["active_governance_domains"]
    assert crowding["crowding_status"] == "crowded"
    assert crowding["crowding_discount"] > 0
    assert crowding["crowding_evidence"]
    assert crowding["crowding_evidence"][0]["symbol"] == "QCOM"
    assert crowding["crowding_evidence"][0]["theme"] == "semiconductor"
    assert crowding["downgrade"] is True
    assert crowding["downgrade_reason"]
    assert "validated_final_candidate" not in crowding
    assert_advisory_subsurface_boundary(crowding, "crowding_governance")
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_every_governance_non_pass_decision_has_explicit_reason(tmp_path: Path) -> None:
    lifecycle_data = {
        "lifecycle_state": "Active",
        "internal_state": "ACTIVE_TRACK",
        "catalyst_state": "Active",
        "stale_event": {"is_stale": True},
    }
    fatigue_data = {
        "fatigue_final": 90,
        "fatigue_score": 90,
        "fatigue_bucket": "high",
        "watch_mode": True,
        "a_minus_1_discount_factor": 0.5,
    }
    payload = {
        "headline": "QCOM jumps",
        "cross_news_conflicts": [
            {
                "symbol": "QCOM",
                "theme": "semiconductor",
                "status": "unresolved",
                "reason": "opposite_direction_news",
                "direction_a": "positive",
                "direction_b": "negative",
                "source_a": "source_a",
                "source_b": "source_b",
                "evidence": "same symbol opposite direction",
            }
        ],
        "crowding_signals": [
            {
                "symbol": "QCOM",
                "theme": "semiconductor",
                "crowded": True,
                "evidence": "theme_overcrowded",
                "candidate_count": 12,
                "threshold": 8,
            }
        ],
    }

    out = _runner(tmp_path, lifecycle_data=lifecycle_data, fatigue_data=fatigue_data).run(payload)
    surface = out["analysis"]["advisory_governance"]

    assert surface["governance_decisions"]
    for decision in surface["governance_decisions"]:
        assert decision["domain"]
        assert decision["source_surface"]
        assert decision["trace_id"]
        assert decision["event_id"]
        if decision["status"] != "pass":
            assert decision["reason"]
