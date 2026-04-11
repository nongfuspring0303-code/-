import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transmission_engine.core.path_adjudicator import PathAdjudicator


def _base_input(paths):
    return {"transmission_paths": paths}


def test_path_adjudicator_outputs_required_fields_and_dominant_contract():
    out = PathAdjudicator().run(
        _base_input(
            [
                {"path_id": "fund_1", "path_name": "fundamental_core", "path_type": "fundamental", "horizon": "1-5D", "persistence": "medium", "confidence": 78.0},
                {"path_id": "asset_1", "path_name": "asset_repricing", "path_type": "asset_pricing", "horizon": "intraday", "persistence": "fast", "confidence": 69.0},
                {"path_id": "narr_1", "path_name": "headline_narrative", "path_type": "narrative", "horizon": "multiweek", "persistence": "slow", "confidence": 55.0},
            ]
        )
    )

    assert out.status.value == "success"
    assert set(["dominant_path", "competing_paths", "suppressed_paths", "mixed_regime"]).issubset(out.data.keys())
    assert set(["name", "confidence", "horizon", "path_type"]).issubset(out.data["dominant_path"].keys())
    assert out.data["dominant_path"]["path_type"] == "fundamental"
    assert out.data["dominant_path"]["confidence"] == round(out.data["dominant_path"]["confidence"], 2)


def test_path_adjudicator_marks_mixed_regime_when_gap_below_min_gap():
    out = PathAdjudicator().run(
        _base_input(
            [
                {"path_id": "fund_1", "path_name": "fundamental_core", "path_type": "fundamental", "horizon": "1-5D", "persistence": "medium", "confidence": 77.0},
                {"path_id": "asset_1", "path_name": "asset_repricing", "path_type": "asset_pricing", "horizon": "intraday", "persistence": "fast", "confidence": 69.5},
                {"path_id": "narr_1", "path_name": "headline_narrative", "path_type": "narrative", "horizon": "multiweek", "persistence": "slow", "confidence": 55.0},
            ]
        )
    )

    assert out.data["mixed_regime"] is True
    assert out.metadata["dominance_gap"] < 12.0


def test_path_adjudicator_blocks_narrative_as_strong_main_path_when_non_narrative_is_weak():
    out = PathAdjudicator().run(
        _base_input(
            [
                {"path_id": "narr_1", "path_name": "headline_narrative", "path_type": "narrative", "horizon": "multiweek", "persistence": "slow", "confidence": 82.0},
                {"path_id": "fund_1", "path_name": "fundamental_core", "path_type": "fundamental", "horizon": "1-5D", "persistence": "medium", "confidence": 44.0},
                {"path_id": "asset_1", "path_name": "asset_repricing", "path_type": "asset_pricing", "horizon": "intraday", "persistence": "fast", "confidence": 46.0},
            ]
        )
    )

    assert out.data["dominant_path"]["path_type"] != "narrative"
    assert any(item["path_type"] == "narrative" for item in out.data["suppressed_paths"])
    assert out.metadata["narrative_guarded"] is True


def test_path_adjudicator_rounds_scores_to_two_decimals():
    out = PathAdjudicator().run(
        _base_input(
            [
                {"path_id": "fund_1", "path_name": "fundamental_core", "path_type": "fundamental", "horizon": "1-5D", "persistence": "medium", "confidence": 77.126},
                {"path_id": "asset_1", "path_name": "asset_repricing", "path_type": "asset_pricing", "horizon": "intraday", "persistence": "fast", "confidence": 66.444},
            ]
        )
    )

    assert out.data["dominant_path"]["confidence"] == 77.13
    assert out.metadata["top1_score"] == 77.13
