from __future__ import annotations

from pathlib import Path

from test_advisory_governance import _runner


def test_cross_news_unresolved_conflict_forces_manual_review_without_final_mutation(tmp_path: Path) -> None:
    payload = {
        "headline": "QCOM jumps",
        "cross_news_conflicts": [
            {"symbol": "QCOM", "theme": "semiconductor", "status": "unresolved", "reason": "opposite_direction_news"}
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
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_crowding_signal_downgrades_without_creating_final_candidate(tmp_path: Path) -> None:
    payload = {
        "headline": "QCOM jumps",
        "crowding_signals": [
            {"symbol": "QCOM", "theme": "semiconductor", "crowded": True, "evidence": "theme_overcrowded"}
        ],
    }
    out = _runner(tmp_path, enable_cross_news_guard=False).run(payload)
    surface = out["analysis"]["advisory_governance"]
    crowding = out["analysis"]["crowding_governance"]

    assert surface["overall_status"] == "downgrade"
    assert "crowding" in surface["active_governance_domains"]
    assert crowding["crowding_status"] == "crowded"
    assert crowding["crowding_discount"] >= 0
    assert crowding["downgrade"] is True
    assert crowding["downgrade_reason"]
    assert "validated_final_candidate" not in crowding
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"
