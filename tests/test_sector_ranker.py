import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transmission_engine.core.sector_ranker import rank_sectors


def test_rank_sectors_outputs_primary_secondary_and_avoid():
    out = rank_sectors(
        [
            {"name": "Technology", "direction": "LONG", "impact_score": 0.9, "confidence": 0.8},
            {"name": "Energy", "direction": "SHORT", "impact_score": 0.7, "confidence": 0.8},
            {"name": "Industrials", "direction": "LONG", "impact_score": 0.5, "confidence": 0.6},
        ]
    )
    assert out["primary_sector"] == "Technology"
    assert out["secondary_sector"] == "Industrials"
    assert "Energy" in out["avoid_sector"]
    assert "Technology" in out["sector_scores"]
