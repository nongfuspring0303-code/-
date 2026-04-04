import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from opportunity_score import OpportunityScorer, PremiumStockPool, evaluate_direction_consistency


def test_premium_pool_filters_by_threshold_and_membership():
    pool = PremiumStockPool()
    candidates = [
        {"symbol": "NVDA"},
        {"symbol": "CAT"},  # market cap below threshold in pool config
        {"symbol": "UNKNOWN"},
    ]
    filtered = pool.filter_candidates(candidates)
    symbols = {s.symbol for s in filtered}
    assert "NVDA" in symbols
    assert "CAT" not in symbols
    assert "UNKNOWN" not in symbols


def test_opportunity_card_fields_complete_and_premium_only():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_b_task_001",
        "schema_version": "v1.0",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.82, "confidence": 0.86},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.75, "confidence": 0.80},
        ],
        "stock_candidates": [
            {"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.3},
            {"symbol": "JPM", "sector": "金融", "direction": "SHORT", "event_beta": 1.1},
            {"symbol": "CAT", "sector": "工业", "direction": "SHORT", "event_beta": 1.2},
        ],
    }

    out = scorer.build_opportunity_update(payload)
    assert out["type"] == "opportunity_update"
    assert out["trace_id"] == "evt_b_task_001"
    assert out["stats"]["premium_pool_only"] is True
    assert out["opportunities"]

    for opp in out["opportunities"]:
        assert set(["symbol", "name", "sector", "signal", "entry_zone", "risk_flags", "final_action", "reasoning", "confidence", "timestamp"]).issubset(opp)
        assert opp["signal"] in ("LONG", "SHORT", "WATCH")
        assert opp["final_action"] in ("EXECUTE", "WATCH", "BLOCK", "PENDING_CONFIRM")
        assert set(["support", "resistance"]).issubset(opp["entry_zone"])


def test_direction_consistency_rate_meets_target():
    scorer = OpportunityScorer()
    bullish = [
        {
            "trace_id": f"bull_{i}",
            "schema_version": "v1.0",
            "sectors": [{"name": "科技", "direction": "LONG", "impact_score": 0.8, "confidence": 0.85}],
            "stock_candidates": [{"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.2}],
        }
        for i in range(20)
    ]
    bearish = [
        {
            "trace_id": f"bear_{i}",
            "schema_version": "v1.0",
            "sectors": [{"name": "科技", "direction": "SHORT", "impact_score": 0.8, "confidence": 0.85}],
            "stock_candidates": [{"symbol": "NVDA", "sector": "科技", "direction": "SHORT", "event_beta": 1.2}],
        }
        for i in range(20)
    ]

    metrics = evaluate_direction_consistency(scorer, bullish, bearish)
    assert metrics["differentiation_rate"] >= 0.8
