import sys
import csv
from pathlib import Path
from typing import Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from opportunity_score import OpportunityScorer, PremiumStock, PremiumStockPool, evaluate_direction_consistency


def _write_pool_config(path: Path, *, dynamic_cache_dir: str, stocks: Optional[List[Dict[str, object]]] = None) -> None:
    payload = {
        "schema_version": "v1.0",
        "version": "v1.0",
        "filters": {
            "roe_min": 15.0,
            "market_cap_billion_min": 50.0,
            "liquidity_score_min": 0.60,
        },
        "price_source": "reference_snapshot",
        "runtime": {"stock_pool": {"dynamic_cache_dir": dynamic_cache_dir}},
        "opportunity_rules": {
            "watch_score_threshold": 0.55,
            "execute_score_threshold": 0.70,
            "support_buffer_pct": 0.03,
            "resistance_buffer_pct": 0.03,
            "max_candidates_per_sector": 5,
        },
        "stocks": stocks or [],
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_history_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


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


def test_premium_pool_keeps_boundary_values():
    pool = PremiumStockPool()
    boundary_stock = PremiumStock(
        symbol="BOUND",
        name="Boundary Co",
        sector="科技",
        roe=15.0,
        market_cap_billion=500.0,
        liquidity_score=0.60,
        last_price=100.0,
    )
    pool._stocks_by_symbol["BOUND"] = boundary_stock
    pool._static_stocks_by_symbol["BOUND"] = boundary_stock

    filtered = pool.filter_candidates([{"symbol": "BOUND"}])
    assert [stock.symbol for stock in filtered] == ["BOUND"]


def test_premium_pool_reports_stock_sources():
    pool = PremiumStockPool()
    static_stock = PremiumStock(
        symbol="STATIC",
        name="Static Co",
        sector="科技",
        roe=20.0,
        market_cap_billion=800.0,
        liquidity_score=0.9,
        last_price=100.0,
    )
    dynamic_stock = PremiumStock(
        symbol="DYNAMIC",
        name="Dynamic Co",
        sector="金融",
        roe=20.0,
        market_cap_billion=800.0,
        liquidity_score=0.9,
        last_price=80.0,
        price_source="dynamic_cache",
    )
    pool._static_stocks_by_symbol["STATIC"] = static_stock
    pool._dynamic_stocks_by_symbol["DYNAMIC"] = dynamic_stock
    pool._stocks_by_symbol["STATIC"] = static_stock
    pool._stocks_by_symbol["DYNAMIC"] = dynamic_stock

    assert pool.get_stock_source("STATIC") == "static"
    assert pool.get_stock_source("DYNAMIC") == "dynamic"
    assert pool.get_stock_source("UNKNOWN") == "unknown"


def test_dynamic_stock_cache_loads_from_configured_directory(tmp_path):
    stock_cache_dir = tmp_path / "stock_cache"
    _write_history_csv(
        stock_cache_dir / "DYNAMIC_history.csv",
        [
            {"close": 101.25, "volume": 1000},
            {"close": 102.50, "volume": 1100},
        ],
    )
    config_path = tmp_path / "pool.yaml"
    _write_pool_config(config_path, dynamic_cache_dir=str(stock_cache_dir))

    pool = PremiumStockPool(pool_config_path=str(config_path))
    stock = pool.get_stock("DYNAMIC")

    assert stock is not None
    assert stock.symbol == "DYNAMIC"
    assert stock.last_price == 102.5
    assert pool.get_stock_source("DYNAMIC") == "dynamic"


def test_static_pool_takes_priority_over_dynamic_pool(tmp_path):
    stock_cache_dir = tmp_path / "stock_cache"
    _write_history_csv(
        stock_cache_dir / "NVDA_history.csv",
        [
            {"close": 99.0, "volume": 1000},
            {"close": 100.0, "volume": 1200},
        ],
    )
    config_path = tmp_path / "pool.yaml"
    _write_pool_config(
        config_path,
        dynamic_cache_dir=str(stock_cache_dir),
        stocks=[
            {
                "symbol": "NVDA",
                "name": "Static NVDA",
                "sector": "科技",
                "roe": 30.0,
                "market_cap_billion": 1000.0,
                "liquidity_score": 0.95,
                "last_price": 999.0,
            }
        ],
    )

    pool = PremiumStockPool(pool_config_path=str(config_path))
    stock = pool.get_stock("NVDA")

    assert stock is not None
    assert stock.name == "Static NVDA"
    assert stock.last_price == 999.0
    assert pool.get_stock_source("NVDA") == "static"


def test_dynamic_load_failure_is_observable(tmp_path, monkeypatch, caplog):
    import pandas as pd

    stock_cache_dir = tmp_path / "stock_cache"
    _write_history_csv(
        stock_cache_dir / "BROKEN_history.csv",
        [{"close": 88.0, "volume": 1000}],
    )
    config_path = tmp_path / "pool.yaml"
    _write_pool_config(config_path, dynamic_cache_dir=str(stock_cache_dir))

    def _boom(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(pd, "read_csv", _boom)
    with caplog.at_level("WARNING"):
        pool = PremiumStockPool(pool_config_path=str(config_path))

    assert pool.get_stock("BROKEN") is None
    assert any("Failed to load stock data for BROKEN" in record.message for record in caplog.records)


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
            {"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.3, "supporting_sector": "科技", "rationale": "NVDA GPUs are directly exposed to AI server demand."},
            {"symbol": "JPM", "sector": "金融", "direction": "SHORT", "event_beta": 1.1, "supporting_sector": "金融", "rationale": "JPM is a direct financial sector proxy for rates and credit spreads."},
            {"symbol": "CAT", "sector": "工业", "direction": "SHORT", "event_beta": 1.2, "supporting_sector": "工业", "rationale": "CAT is directly exposed to industrial equipment demand."},
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
            "stock_candidates": [{"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.2, "supporting_sector": "科技", "rationale": "NVDA GPUs are directly exposed to AI server demand."}],
        }
        for i in range(20)
    ]
    bearish = [
        {
            "trace_id": f"bear_{i}",
            "schema_version": "v1.0",
            "sectors": [{"name": "科技", "direction": "SHORT", "impact_score": 0.8, "confidence": 0.85}],
            "stock_candidates": [{"symbol": "NVDA", "sector": "科技", "direction": "SHORT", "event_beta": 1.2, "supporting_sector": "科技", "rationale": "NVDA GPUs are directly exposed to AI server demand."}],
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
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
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
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)
    assert len(out["opportunities"]) == 1
    opp = out["opportunities"][0]

    assert opp["entry_zone"] == {"support": 485.0, "resistance": 515.0}
    assert opp["price_source"] == "live"
    assert opp["needs_price_refresh"] is False


def test_price_fetch_disabled_does_not_call_adapter():
    scorer = OpportunityScorer()

    class FailingAdapter:
        def quote_one(self, _symbol):
            raise AssertionError("quote_one should not be called when price fetch is disabled")

        def quote_many_with_context(self, _symbols, trace_id=None, request_id=None):
            raise AssertionError("quote_many_with_context should not be called when price fetch is disabled")

    scorer._price_fetch_enabled = False
    scorer._market_data_adapter = FailingAdapter()

    payload = {
        "trace_id": "evt_price_fetch_disabled",
        "schema_version": "v1.0",
        "sectors": [{"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.9}],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.3,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)
    assert len(out["opportunities"]) == 1
    opp = out["opportunities"][0]
    assert opp["final_action"] == "WATCH"
    assert any(f.get("type") == "price_data" for f in opp["risk_flags"])


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


def test_premium_stock_pool_supports_extended_sector_aliases():
    pool = PremiumStockPool()
    assert {stock.symbol for stock in pool.pick_by_sector("新能源")} >= {"TSLA"}
    assert {stock.symbol for stock in pool.pick_by_sector("原材料")} >= {"FCX", "SCCO"}
    assert {stock.symbol for stock in pool.pick_by_sector("通信服务")} >= {"NFLX"}
    assert {stock.symbol for stock in pool.pick_by_sector("房地产")} >= {"AMT"}


def test_opportunity_output_contains_gate_and_score_fields():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_gate_fields",
        "schema_version": "v1.1",
        "news_timestamp": "2026-04-11T00:00:00Z",
        "sectors": [{"name": "Technology", "direction": "LONG", "impact_score": 0.8, "confidence": 0.9}],
        "stock_candidates": [{"symbol": "NVDA", "sector": "Technology", "direction": "LONG", "event_beta": 1.2, "supporting_sector": "Technology", "rationale": "NVDA GPUs are directly exposed to AI server demand."}],
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
        "stock_candidates": [{"symbol": "NVDA", "sector": "Technology", "direction": "LONG", "event_beta": 1.2, "supporting_sector": "Technology", "rationale": "NVDA GPUs are directly exposed to AI server demand."}],
        "asset_validation": "invalid-shape",
    }
    out = scorer.build_opportunity_update(payload)
    assert out["action"] in {"WATCH", "NO_ACTION", "TRADE"}


def test_opportunity_update_propagates_event_identity_and_primary_sector_only():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_identity_primary",
        "event_hash": "evt_hash_identity_primary",
        "semantic_trace_id": "evt_live_identity_primary",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.95, "role": "primary"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.85, "confidence": 0.9, "role": "secondary"},
        ],
        "stock_candidates": [
            {"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.4},
            {"symbol": "JPM", "sector": "金融", "direction": "SHORT", "event_beta": 1.1},
        ],
    }

    out = scorer.build_opportunity_update(payload)

    assert out["event_hash"] == "evt_hash_identity_primary"
    assert out["semantic_trace_id"] == "evt_live_identity_primary"
    assert out["primary_sector"] == "科技"
    assert len(out["audit_sectors"]) == 2
    assert out["audit_sectors"][0]["role"] == "primary"
    assert out["audit_sectors"][1]["role"] == "secondary"
    assert out["policy_state"]["threshold_status"] == "proposed"
    assert out["policy_state"]["enforcement_mode"] == "observe_only"
    assert out["policy_state"]["primary_sector_only"] is True
    assert out["opportunities"]
    assert {opp["sector"] for opp in out["opportunities"]} == {"科技"}
    assert all(opp["event_hash"] == "evt_hash_identity_primary" for opp in out["opportunities"])
    assert all(opp["semantic_trace_id"] == "evt_live_identity_primary" for opp in out["opportunities"])
    assert all(opp["sector_role"] == "primary" for opp in out["opportunities"])


def test_opportunity_update_missing_event_hash_does_not_fallback():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_missing_event_hash",
        "semantic_trace_id": "evt_live_missing_event_hash",
        "schema_version": "v1.0",
        "sectors": [{"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.95}],
        "stock_candidates": [{"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.4}],
    }

    out = scorer.build_opportunity_update(payload)

    assert out["event_hash"] == ""
    assert out["semantic_trace_id"] == "evt_live_missing_event_hash"
    assert out["identity_incomplete"] is True
    assert out["strict_join_ready"] is False
    assert "missing_event_hash" in out["missing_identity_reasons"]
    assert out["opportunities"]


def test_opportunity_update_missing_semantic_trace_id_does_not_fake_join():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_missing_semantic_trace",
        "event_hash": "evt_hash_missing_semantic",
        "schema_version": "v1.0",
        "sectors": [{"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.95}],
        "stock_candidates": [{"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.4}],
    }

    out = scorer.build_opportunity_update(payload)

    assert out["event_hash"] == "evt_hash_missing_semantic"
    assert out["semantic_trace_id"] == ""
    assert out["identity_incomplete"] is True
    assert out["strict_join_ready"] is False
    assert "missing_semantic_trace_id" in out["missing_identity_reasons"]


def test_opportunity_update_policy_missing_config_does_not_silently_enable_defaults():
    scorer = OpportunityScorer()
    scorer._semantic_chain_policy = {
        "schema_version": "semantic_chain_policy.v1",
        "threshold_status": "proposed",
        "enforcement_mode": "disabled",
        "policy_load_status": "failed",
        "policy_error_reason": "missing_config",
        "audit": {
            "primary_sector_only": False,
            "secondary_sector_audit_only": False,
        },
    }
    payload = {
        "trace_id": "evt_policy_missing",
        "event_hash": "evt_hash_policy_missing",
        "semantic_trace_id": "evt_live_policy_missing",
        "schema_version": "v1.0",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.95, "role": "primary"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.85, "confidence": 0.9, "role": "secondary"},
        ],
        "stock_candidates": [
            {"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.4},
            {"symbol": "JPM", "sector": "金融", "direction": "SHORT", "event_beta": 1.1},
        ],
    }

    out = scorer.build_opportunity_update(payload)

    assert out["policy_state"]["policy_load_status"] == "failed"
    assert out["policy_state"]["enforcement_mode"] == "disabled"
    assert out["policy_state"]["primary_sector_only"] is False
    assert out["policy_state"]["policy_error_reason"] == "missing_config"
    assert {opp["sector_role"] for opp in out["opportunities"]} == {"primary", "secondary"}


def test_opportunity_update_policy_invalid_config_does_not_silently_enable_defaults():
    scorer = OpportunityScorer()
    scorer._semantic_chain_policy = {
        "schema_version": "semantic_chain_policy.v1",
        "threshold_status": "proposed",
        "enforcement_mode": "disabled",
        "policy_load_status": "failed",
        "policy_error_reason": "invalid_config",
        "audit": {
            "primary_sector_only": False,
            "secondary_sector_audit_only": False,
        },
    }
    payload = {
        "trace_id": "evt_policy_invalid",
        "event_hash": "evt_hash_policy_invalid",
        "semantic_trace_id": "evt_live_policy_invalid",
        "schema_version": "v1.0",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.9, "confidence": 0.95, "role": "primary"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.85, "confidence": 0.9, "role": "secondary"},
        ],
        "stock_candidates": [
            {"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.4},
            {"symbol": "JPM", "sector": "金融", "direction": "SHORT", "event_beta": 1.1},
        ],
    }

    out = scorer.build_opportunity_update(payload)

    assert out["policy_state"]["policy_load_status"] == "failed"
    assert out["policy_state"]["enforcement_mode"] == "disabled"
    assert out["policy_state"]["primary_sector_only"] is False
    assert out["policy_state"]["policy_error_reason"] == "invalid_config"
    assert {opp["sector_role"] for opp in out["opportunities"]} == {"primary", "secondary"}


def test_pr124_primary_sector_ticker_allowed_with_supporting_sector_and_rationale():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_pr124_ticker_allowed",
        "event_hash": "evt_hash_pr124_ticker_allowed",
        "semantic_trace_id": "evt_live_pr124_ticker_allowed",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.92, "confidence": 0.95, "role": "primary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
                "sector_score_source": "semantic_sector",
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)

    assert out["template_guard_state"]["policy_load_status"] == "loaded"
    assert out["event_hash"] == "evt_hash_pr124_ticker_allowed"
    assert out["semantic_trace_id"] == "evt_live_pr124_ticker_allowed"
    assert out["opportunities"]
    opp = out["opportunities"][0]
    assert opp["symbol"] == "NVDA"
    assert opp["ticker_guard_status"] == "ticker_allowed"
    assert opp["ticker_guard_reason"] == ""
    assert opp["supporting_sector"] == "科技"
    assert opp["rationale"] == "NVDA GPUs are directly exposed to AI server demand."
    assert opp["support_score"] is None
    assert opp["sector_score_source"] == "semantic_sector"


def test_pr124_multi_sector_secondary_falls_back_to_sector_only_even_with_support():
    scorer = OpportunityScorer()
    scorer._semantic_chain_policy = {
        "schema_version": "semantic_chain_policy.v1",
        "threshold_status": "proposed",
        "enforcement_mode": "observe_only",
        "policy_load_status": "loaded",
        "policy_error_reason": "",
        "audit": {
            "primary_sector_only": False,
            "secondary_sector_audit_only": False,
        },
    }
    payload = {
        "trace_id": "evt_pr124_multi_sector_secondary_support",
        "event_hash": "evt_hash_pr124_multi_sector_secondary_support",
        "semantic_trace_id": "evt_live_pr124_multi_sector_secondary_support",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.93, "confidence": 0.96, "role": "primary", "sector_score_source": "semantic_sector"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.88, "confidence": 0.92, "role": "secondary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
                "sector_score_source": "semantic_sector",
            },
            {
                "symbol": "JPM",
                "sector": "金融",
                "direction": "SHORT",
                "event_beta": 1.1,
                "supporting_sector": "金融",
                "rationale": "JPM is a direct financial sector proxy for rates and credit spreads.",
                "sector_score_source": "semantic_sector",
            },
        ],
    }

    out = scorer.build_opportunity_update(payload)

    secondary = next(opp for opp in out["opportunities"] if opp["sector_role"] == "secondary")
    assert secondary.get("symbol", "") == ""
    assert secondary["ticker_guard_status"] == "sector_only"
    assert "secondary_sector_audit_only" in secondary["ticker_guard_reason"]
    assert secondary["sector_score_source"] == "semantic_sector"


def test_pr124_multi_sector_secondary_template_rationale_falls_back_to_sector_only():
    scorer = OpportunityScorer()
    scorer._semantic_chain_policy = {
        "schema_version": "semantic_chain_policy.v1",
        "threshold_status": "proposed",
        "enforcement_mode": "observe_only",
        "policy_load_status": "loaded",
        "policy_error_reason": "",
        "audit": {
            "primary_sector_only": False,
            "secondary_sector_audit_only": False,
        },
    }
    payload = {
        "trace_id": "evt_pr124_multi_sector_secondary_template",
        "event_hash": "evt_hash_pr124_multi_sector_secondary_template",
        "semantic_trace_id": "evt_live_pr124_multi_sector_secondary_template",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.93, "confidence": 0.96, "role": "primary", "sector_score_source": "semantic_sector"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.88, "confidence": 0.92, "role": "secondary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
                "sector_score_source": "semantic_sector",
            },
            {
                "symbol": "JPM",
                "sector": "金融",
                "direction": "SHORT",
                "event_beta": 1.1,
                "supporting_sector": "金融",
                "rationale": "该公司属于科技板块",
                "sector_score_source": "semantic_sector",
            },
        ],
    }

    out = scorer.build_opportunity_update(payload)

    secondary = next(opp for opp in out["opportunities"] if opp["sector_role"] == "secondary")
    assert secondary.get("symbol", "") == ""
    assert secondary["ticker_guard_status"] == "sector_only"
    assert "template_rationale" in secondary["ticker_guard_reason"]
    assert "secondary_sector_audit_only" in secondary["ticker_guard_reason"]
    assert secondary["sector_score_source"] == "semantic_sector"


def test_pr124_missing_supporting_sector_or_rationale_falls_back_to_sector_only():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_pr124_sector_only",
        "event_hash": "evt_hash_pr124_sector_only",
        "semantic_trace_id": "evt_live_pr124_sector_only",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.88, "confidence": 0.91, "role": "primary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {"symbol": "NVDA", "sector": "科技", "direction": "LONG", "event_beta": 1.4, "sector_score_source": "semantic_sector"}
        ],
    }

    out = scorer.build_opportunity_update(payload)

    assert out["event_hash"] == "evt_hash_pr124_sector_only"
    assert out["semantic_trace_id"] == "evt_live_pr124_sector_only"
    assert out["opportunities"]
    opp = out["opportunities"][0]
    assert opp.get("symbol", "") == ""
    assert opp["ticker_guard_status"] == "sector_only"
    assert "missing_rationale" in opp["ticker_guard_reason"]
    assert "missing_supporting_sector" in opp["ticker_guard_reason"]
    assert opp["supporting_sector"] == "科技"
    assert opp["rationale"].startswith("sector-only fallback:")


def test_pr124_template_rationale_falls_back_to_sector_only():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_pr124_template_guard",
        "event_hash": "evt_hash_pr124_template_guard",
        "semantic_trace_id": "evt_live_pr124_template_guard",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.88, "confidence": 0.91, "role": "primary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "该公司属于科技板块",
                "sector_score_source": "semantic_sector",
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)

    opp = out["opportunities"][0]
    assert opp.get("symbol", "") == ""
    assert opp["ticker_guard_status"] == "sector_only"
    assert "template_rationale" in opp["ticker_guard_reason"]
    assert opp["rationale"].startswith("sector-only fallback:")


def test_pr124_legacy_event_broadcast_does_not_enter_opportunity_output():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_pr124_legacy_broadcast",
        "event_hash": "evt_hash_pr124_legacy_broadcast",
        "semantic_trace_id": "evt_live_pr124_legacy_broadcast",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.86, "confidence": 0.9, "role": "primary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
                "legacy_event_broadcast": True,
                "sector_score_source": "legacy_event_broadcast",
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)

    opp = out["opportunities"][0]
    assert opp.get("symbol", "") == ""
    assert opp["ticker_guard_status"] == "sector_only"
    assert opp["sector_score_source"] != "legacy_event_broadcast"
    assert "legacy_event_broadcast" in opp["ticker_guard_reason"]


def test_pr124_support_score_missing_does_not_block_ticker():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_pr124_support_score_optional",
        "event_hash": "evt_hash_pr124_support_score_optional",
        "semantic_trace_id": "evt_live_pr124_support_score_optional",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.93, "confidence": 0.96, "role": "primary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
            }
        ],
    }

    out = scorer.build_opportunity_update(payload)

    opp = out["opportunities"][0]
    assert opp["symbol"] == "NVDA"
    assert opp["ticker_guard_status"] == "ticker_allowed"
    assert opp["support_score"] is None


def test_pr124_secondary_sector_without_supporting_evidence_defaults_to_sector_only():
    scorer = OpportunityScorer()
    scorer._semantic_chain_policy = {
        "schema_version": "semantic_chain_policy.v1",
        "threshold_status": "proposed",
        "enforcement_mode": "disabled",
        "policy_load_status": "failed",
        "policy_error_reason": "missing_config",
        "audit": {
            "primary_sector_only": False,
            "secondary_sector_audit_only": False,
        },
    }
    payload = {
        "trace_id": "evt_pr124_secondary_sector_only",
        "event_hash": "evt_hash_pr124_secondary_sector_only",
        "semantic_trace_id": "evt_live_pr124_secondary_sector_only",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.92, "confidence": 0.95, "role": "primary", "sector_score_source": "semantic_sector"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.84, "confidence": 0.9, "role": "secondary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
                "sector_score_source": "semantic_sector",
            },
            {
                "symbol": "JPM",
                "sector": "金融",
                "direction": "SHORT",
                "event_beta": 1.1,
                "sector_score_source": "semantic_sector",
            },
        ],
    }

    out = scorer.build_opportunity_update(payload)

    secondary_opp = next(opp for opp in out["opportunities"] if opp["sector"] == "金融")
    assert secondary_opp["sector_role"] == "secondary"
    assert secondary_opp.get("symbol", "") == ""
    assert secondary_opp["ticker_guard_status"] == "sector_only"
    assert "missing_supporting_sector" in secondary_opp["ticker_guard_reason"]
    assert "missing_rationale" in secondary_opp["ticker_guard_reason"]


def test_pr124_multi_sector_requires_sector_scoped_rationale_and_supporting_sector():
    scorer = OpportunityScorer()
    scorer._semantic_chain_policy = {
        "schema_version": "semantic_chain_policy.v1",
        "threshold_status": "proposed",
        "enforcement_mode": "disabled",
        "policy_load_status": "failed",
        "policy_error_reason": "missing_config",
        "audit": {
            "primary_sector_only": False,
            "secondary_sector_audit_only": False,
        },
    }
    payload = {
        "trace_id": "evt_pr124_multi_sector_scope",
        "event_hash": "evt_hash_pr124_multi_sector_scope",
        "semantic_trace_id": "evt_live_pr124_multi_sector_scope",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.92, "confidence": 0.95, "role": "primary", "sector_score_source": "semantic_sector"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.84, "confidence": 0.9, "role": "secondary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
                "sector_score_source": "semantic_sector",
            },
            {
                "symbol": "JPM",
                "sector": "金融",
                "direction": "SHORT",
                "event_beta": 1.1,
                "supporting_sector": "科技",
                "rationale": "JPM is a direct financial sector proxy for rates and credit spreads.",
                "sector_score_source": "semantic_sector",
            },
        ],
    }

    out = scorer.build_opportunity_update(payload)

    primary_opp = next(opp for opp in out["opportunities"] if opp["sector"] == "科技")
    secondary_opp = next(opp for opp in out["opportunities"] if opp["sector"] == "金融")

    assert primary_opp["symbol"] == "NVDA"
    assert primary_opp["ticker_guard_status"] == "ticker_allowed"

    assert secondary_opp.get("symbol", "") == ""
    assert secondary_opp["ticker_guard_status"] == "sector_only"
    assert "secondary_sector_audit_only" in secondary_opp["ticker_guard_reason"]
    assert secondary_opp["supporting_sector"] == "科技"
    assert secondary_opp["rationale"] == "JPM is a direct financial sector proxy for rates and credit spreads."


def test_pr124_multi_sector_template_fallback_does_not_allow_secondary_ticker():
    scorer = OpportunityScorer()
    scorer._semantic_chain_policy = {
        "schema_version": "semantic_chain_policy.v1",
        "threshold_status": "proposed",
        "enforcement_mode": "disabled",
        "policy_load_status": "failed",
        "policy_error_reason": "missing_config",
        "audit": {
            "primary_sector_only": False,
            "secondary_sector_audit_only": False,
        },
    }
    payload = {
        "trace_id": "evt_pr124_multi_sector_template",
        "event_hash": "evt_hash_pr124_multi_sector_template",
        "semantic_trace_id": "evt_live_pr124_multi_sector_template",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {"name": "科技", "direction": "LONG", "impact_score": 0.92, "confidence": 0.95, "role": "primary", "sector_score_source": "semantic_sector"},
            {"name": "金融", "direction": "SHORT", "impact_score": 0.84, "confidence": 0.9, "role": "secondary", "sector_score_source": "semantic_sector"},
        ],
        "stock_candidates": [
            {
                "symbol": "NVDA",
                "sector": "科技",
                "direction": "LONG",
                "event_beta": 1.4,
                "supporting_sector": "科技",
                "rationale": "NVDA GPUs are directly exposed to AI server demand.",
                "sector_score_source": "semantic_sector",
            },
            {
                "symbol": "JPM",
                "sector": "金融",
                "direction": "SHORT",
                "event_beta": 1.1,
                "supporting_sector": "金融",
                "rationale": "该公司属于金融板块",
                "sector_score_source": "semantic_sector",
            },
        ],
    }

    out = scorer.build_opportunity_update(payload)

    secondary_opp = next(opp for opp in out["opportunities"] if opp["sector"] == "金融")
    assert secondary_opp.get("symbol", "") == ""
    assert secondary_opp["ticker_guard_status"] == "sector_only"
    assert "secondary_sector_audit_only" in secondary_opp["ticker_guard_reason"]
