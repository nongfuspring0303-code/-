import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transmission_engine.core.stock_exposure_model import build_stock_candidates


def test_build_stock_candidates_uses_event_exposure_and_limits_to_five():
    payload = {
        "event_type_lv2": "AI_CAPEX_UP",
        "stock_candidates": [
            {"symbol": "NVDA", "direction": "LONG"},
            {"symbol": "AVGO", "direction": "LONG"},
            {"symbol": "META", "direction": "LONG"},
            {"symbol": "MSFT", "direction": "LONG"},
            {"symbol": "AAPL", "direction": "LONG"},
            {"symbol": "GOOGL", "direction": "LONG"},
        ],
    }
    rankings = {"primary_sector": "科技"}
    out = build_stock_candidates(payload, rankings, max_candidates=5)
    assert len(out) <= 5
    assert out
    assert out[0]["symbol"] in {"NVDA", "AVGO", "META"}
    assert "stock_transmission_score" in out[0]
    assert "score_breakdown" in out[0]
