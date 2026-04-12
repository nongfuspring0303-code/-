import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from opportunity_score import OpportunityScorer, PremiumStockPool, evaluate_direction_consistency


def test_premium_pool_filters_by_threshold_and_membership():
    pool = PremiumStockPool()
    assert pool.price_source == "reference_snapshot"
    candidates = [
        {"symbol": "NVDA"},
        {"symbol": "CAT"},
        {"symbol": "UNKNOWN"},
    ]
    filtered = pool.filter_candidates(candidates)
    symbols = {s.symbol for s in filtered}
    assert "NVDA" in symbols
    assert "CAT" in symbols
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


def test_missing_realtime_price_forces_watch_with_risk_flag():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_missing_realtime_price",
        "schema_version": "v1.0",
        "sectors": [{"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.9}],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.3,
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)
    assert len(out["opportunities"]) == 1
    opp = out["opportunities"][0]

    assert opp["final_action"] == "WATCH"
    assert any(f.get("type") == "price_data" for f in opp["risk_flags"])


def test_entry_zone_uses_realtime_price_first():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_realtime_price_first",
        "schema_version": "v1.0",
        "sectors": [{"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.9}],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.3,
                "realtime_price": 500.0,
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)
    assert len(out["opportunities"]) == 1
    opp = out["opportunities"][0]

    assert opp["entry_zone"] == {"support": 485.0, "resistance": 515.0}
    assert opp["price_source"] == "live"
    assert opp["needs_price_refresh"] is False


def test_fallback_pool_supports_sector_alias_dictionary():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_energy_alias",
        "schema_version": "v1.0",
        "sectors": [{"name": "Energy", "direction": "LONG", "impact_score": 0.8, "confidence": 0.8}],
        "stock_candidates": [],
    }

    out = scorer.build_opportunity_update(payload)
    assert any(opp["symbol"] == "XOM" for opp in out["opportunities"])


def test_opportunity_output_contains_gate_and_score_fields():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_gate_fields",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "sectors": [{"name": "Technology", "direction": "LONG", "impact_score": 0.8, "confidence": 0.9}],
        "stock_candidates": [{"symbol": "NVDA", "sector": "Technology", "direction": "LONG", "event_beta": 1.2}],
        "asset_validation": {"score": 80},
        "mixed_regime": False,
    }
    out = scorer.build_opportunity_update(payload)

    assert "action" in out
    assert "state_machine_step" in out
    assert "gate_reason_code" in out
    assert "stats" in out
    assert "grade_counts" in out["stats"]
    assert set(out["stats"]["grade_counts"].keys()) == {"A", "B", "C"}
    assert out["opportunities"]

    first = out["opportunities"][0]
    assert "score_100" in first
    assert "signal_grade" in first
    assert "score_breakdown" in first
    assert "state_machine_step" in first
    assert "gate_reason_code" in first


def test_opportunity_handles_invalid_asset_validation_shape_defensively():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_invalid_asset_validation",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "sectors": [{"name": "Technology", "direction": "LONG", "impact_score": 0.8, "confidence": 0.9}],
        "stock_candidates": [{"symbol": "NVDA", "sector": "Technology", "direction": "LONG", "event_beta": 1.2}],
        "asset_validation": "invalid-shape",
    }
    out = scorer.build_opportunity_update(payload)
    assert out["action"] in {"WATCH", "NO_ACTION", "TRADE"}
