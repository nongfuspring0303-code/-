import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def test_conduction_mapper_uses_chain_template_for_trade_war():
    out = ConductionMapper().run(
        {
            "event_id": "ME-C-TEST-001",
            "category": "C",
            "severity": "E3",
            "headline": "Trade war escalates after new tariffs",
            "summary": "Tariff escalation affects exporters",
            "lifecycle_state": "Active",
            "sector_data": [
                {"sector": "Industrials", "industry": "Industrials"},
                {"sector": "Technology", "industry": "Technology"},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:tariff_chain"
    assert out.data["conduction_path"]
    assert out.data["sector_impacts"]


def test_conduction_mapper_matches_rate_cut_template():
    out = ConductionMapper().run(
        {
            "event_id": "ME-E-TEST-002",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"sector": "Technology", "industry": "Technology"},
                {"sector": "Financial Services", "industry": "Financial Services"},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:rate_cut_chain"
    assert out.data["sector_impacts"]


def test_conduction_mapper_uses_trade_talks_chain_for_meeting_context():
    out = ConductionMapper().run(
        {
            "event_id": "ME-C-TEST-003",
            "category": "C",
            "severity": "E2",
            "headline": "Trump-Xi trade meeting to discuss capital flows",
            "summary": "双方将进行贸易谈判",
            "lifecycle_state": "Active",
            "sector_data": [
                {"sector": "Industrials", "industry": "Industrials"},
                {"sector": "Consumer Cyclical", "industry": "Consumer Cyclical"},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:trade_talks_chain"


def test_conduction_mapper_ignores_unknown_semantic_chain_and_keeps_rule_match(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "unknown_chain",
            "confidence": 95,
            "event_type": "other",
            "sentiment": "neutral",
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-C-TEST-004",
            "category": "C",
            "severity": "E2",
            "headline": "Trump-Xi trade meeting to discuss capital flows",
            "summary": "双方将进行贸易谈判",
            "lifecycle_state": "Active",
            "sector_data": [{"sector": "Industrials", "industry": "Industrials"}],
        }
    )
    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:trade_talks_chain"


def test_conduction_mapper_picks_reloaded_chain_config(tmp_path):
    mapper = ConductionMapper()
    cfg = {
        "chain_templates": [
            {
                "id": "custom_chain",
                "name": "custom",
                "levels": [
                    {"level": "macro", "name": "m", "factors": []},
                    {"level": "sector", "name": "s", "sectors": [{"name": "Technology", "direction": "benefit", "impact_score": 0.8}]},
                ],
            }
        ],
        "event_to_chain_mapping": [
            {"event_keywords": ["custom trigger"], "chain_id": "custom_chain"}
        ],
    }
    path = tmp_path / "conduction_chain.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    mapper.chain_config_path = path
    mapper.config_center.register("conduction_chain", path)

    out = mapper.run(
        {
            "event_id": "ME-T-TEST-001",
            "category": "T",
            "severity": "E2",
            "headline": "This has custom trigger",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [{"sector": "Technology", "industry": "Technology"}],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:custom_chain"


def test_conduction_mapper_standardizes_ai_recommendations(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain",
            "recommended_stocks": ["nvda", "aapl", "NVDA"],
            "confidence": 95,
            "event_type": "monetary",
            "sentiment": "positive",
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-E-TEST-006",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 1.2},
                {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.8},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["ai_recommendation_source"] == "semantic_analyzer"
    assert out.data["ai_recommendation_chain"] == "rate_cut_chain"
    assert out.data["ai_recommended_stocks"] == ["NVDA", "AAPL"]


def test_conduction_mapper_injects_semantic_candidates_into_stock_candidates(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain",
            "recommended_stocks": ["NVDA"],
            "entities": [{"type": "ticker", "value": "AAPL"}],
            "transmission_candidates": ["risk_appetite", "leader_momentum"],
            "novelty_score": 0.7,
            "confidence": 91,
            "event_type": "monetary",
            "sentiment": "positive",
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-E-TEST-007",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 1.2},
                {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.8},
            ],
        }
    )

    assert out.status.value == "success"
    symbols = [str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])]
    assert "NVDA" in symbols
    assert "AAPL" in symbols


def test_conduction_mapper_keeps_semantic_chain_when_event_type_other(monkeypatch):
    # Rule/Test mapping: R93-SEM-002 / T-R93-SEM-002 (regression-only)
    # Regression guard: for event_type=other, a valid semantic recommended_chain should still drive template mapping.
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain",
            "recommended_stocks": ["NVDA", "AAPL"],
            "confidence": 90,
            "event_type": "other",
            "sentiment": "neutral",
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-E-TEST-009",
            "category": "E",
            "severity": "E2",
            "headline": "Generic macro update without explicit event keyword",
            "summary": "market volatility update",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 1.2},
                {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.8},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:rate_cut_chain"
    assert out.data["ai_recommendation_chain"] == "rate_cut_chain"
    symbols = [str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])]
    assert "NVDA" in symbols
    assert "AAPL" in symbols


def test_conduction_mapper_filters_invalid_semantic_values(monkeypatch):
    # Rule/Test mapping: R93-SEM-003 / T-R93-SEM-003 (regression-only)
    # Regression guard: invalid semantic stock/entity values must be filtered before stock_candidates output.
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain",
            "recommended_stocks": ["", None, "nvda", "N/A", 123, "aapl", "NVDA"],
            "entities": [
                {"type": "ticker", "value": "AAPL"},
                {"type": "company", "value": "Google"},
                {"type": "symbol", "value": ""},
                {"type": "stock", "value": None},
                {"type": "person", "value": "Jerome Powell"},
            ],
            "transmission_candidates": ["risk_appetite"],
            "novelty_score": 0.5,
            "confidence": 80,
            "event_type": "monetary",
            "sentiment": "positive",
        },
    )
    monkeypatch.setattr(
        mapper,
        "_policy_mapping",
        lambda policy_intervention, sector_data: {
            "macro_factors": [{"factor": "rates", "direction": "down", "strength": "medium", "reason": "stub"}],
            "asset_impacts": [],
            "sector_impacts": [{"sector": "Financial Services", "direction": "benefit", "driver_type": "beta", "reason": "stub"}],
            "stock_candidates": [],
            "conduction_path": ["stub"],
            "confidence": 74,
        },
    )
    out = mapper.run({
        "event_id": "ME-E-TEST-008",
        "category": "E",
        "severity": "E2",
        "headline": "Fed signals rate cuts ahead",
        "summary": "Policy easing expected",
        "lifecycle_state": "Active",
        "sector_data": [{"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.8}],
    })
    assert out.status.value == "success"
    candidates = out.data.get("stock_candidates", [])
    symbols = [str(x.get("symbol", "")).upper() for x in candidates]
    assert "NVDA" in symbols
    assert "AAPL" in symbols
    assert "N/A" not in symbols
    assert "123" not in symbols
    assert "" not in symbols
    assert out.data.get("audit", {}).get("ai_entity_stocks") is None


def test_trade_talk_context_not_overridden_by_broad_tariff_tokens():
    out = ConductionMapper().run(
        {
            "event_id": "ME-C-TEST-005",
            "category": "C",
            "severity": "E2",
            "headline": "US-China trade talks meeting discusses tariff framework",
            "summary": "双方会晤以谈判为主，暂无升级措施",
            "lifecycle_state": "Active",
            "sector_data": [
                {"sector": "Industrials", "industry": "Industrials"},
                {"sector": "Consumer Cyclical", "industry": "Consumer Cyclical"},
            ],
        }
    )
    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:trade_talks_chain"


def test_conduction_mapper_semantic_event_type_fallback_for_energy(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "confidence": 83,
            "event_type": "energy",
            "sentiment": "negative",
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-X-TEST-ENERGY-001",
            "category": "X",
            "severity": "E2",
            "headline": "Generic supply disruption update",
            "summary": "No direct chain keyword in headline",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 1.1},
                {"symbol": "CAT", "sector": "Industrials", "industry": "Industrials", "change_pct": 0.4},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:energy_supply_chain"
    sectors = [str(x.get("sector", "")) for x in out.data.get("sector_impacts", [])]
    assert "Energy" in sectors


def test_conduction_mapper_commodity_keyword_routes_to_commodity_chain_not_healthcare():
    out = ConductionMapper().run(
        {
            "event_id": "ME-X-TEST-COMM-001",
            "category": "X",
            "severity": "E2",
            "headline": "Spot silver surges 3% as commodity market rallies",
            "summary": "现货白银大涨，商品价格冲击扩大",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 0.7},
                {"symbol": "LIN", "sector": "Materials", "industry": "Materials", "change_pct": 0.6},
                {"symbol": "LLY", "sector": "Healthcare", "industry": "Healthcare", "change_pct": 0.2},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:commodity_price_chain"
    sectors = [str(x.get("sector", "")) for x in out.data.get("sector_impacts", [])]
    assert "Healthcare" not in sectors
    assert "Energy" in sectors or "Materials" in sectors


def test_conduction_mapper_outputs_sector_weights_and_primary_secondary(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "confidence": 86,
            "event_type": "energy",
            "sentiment": "negative",
            "transmission_candidates": ["oil supply disruption"],
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-X-TEST-WEIGHT-001",
            "category": "X",
            "severity": "E2",
            "headline": "Oil supply disruption pushes crude higher",
            "summary": "OPEC output cut",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 1.0}],
        }
    )
    assert out.status.value == "success"
    assert isinstance(out.data.get("sector_weights"), dict)
    assert out.data.get("primary_sector")
    assert isinstance(out.data.get("secondary_sectors"), list)
    assert out.data.get("semantic_subtype") in {"crude_oil", "oil_supply_disruption", ""}


def test_conduction_mapper_adds_ticker_pool_candidates_for_tier1(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 91,
            "event_type": "commodity",
            "sentiment": "positive",
            "transmission_candidates": ["gold price surge"],
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-X-TEST-POOL-001",
            "category": "X",
            "severity": "E2",
            "headline": "Gold surges to record as safe-haven demand rises",
            "summary": "gold and miners rally",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "NEM", "sector": "Materials", "industry": "Materials", "change_pct": 1.2}],
        }
    )
    assert out.status.value == "success"
    candidates = out.data.get("stock_candidates", [])
    assert candidates
    assert any(c.get("source") == "tier1_ticker_pool" for c in candidates)


def test_other_event_defaults_to_watchlist_and_not_recommended(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 80,
            "event_type": "other",
            "sentiment": "neutral",
            "transmission_candidates": [],
        },
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-OTHER-001",
            "category": "X",
            "severity": "E2",
            "headline": "General market update with no clear sector driver",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 0.5}],
        }
    )
    buckets = out.data.get("stock_recommendation_buckets", {})
    assert isinstance(buckets.get("recommended", []), list)
    assert len(buckets.get("recommended", [])) == 0


def test_tech_event_defaults_to_watchlist_without_direct_mention(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 85,
            "event_type": "tech",
            "sentiment": "positive",
            "transmission_candidates": [],
        },
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-TECH-001",
            "category": "X",
            "severity": "E2",
            "headline": "Semiconductor ecosystem update",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "NVDA", "sector": "Technology", "industry": "Technology", "change_pct": 0.6}],
        }
    )
    buckets = out.data.get("stock_recommendation_buckets", {})
    # Tech is now Tier1 — it should recommend even without direct mention
    assert len(buckets.get("recommended", [])) > 0, "Tier1 tech should recommend stocks"


def test_sector_impacts_deduplicated(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 80,
            "event_type": "other",
            "sentiment": "neutral",
            "transmission_candidates": [],
        },
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-DEDUP-001",
            "category": "E",
            "severity": "E2",
            "headline": "policy easing update",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 0.7},
                {"symbol": "CVX", "sector": "Energy", "industry": "Energy", "change_pct": 0.6},
            ],
        }
    )
    sectors = [str(x.get("sector", "")) for x in out.data.get("sector_impacts", [])]
    assert sectors.count("Energy") <= 1


def test_asia_tech_headline_rejects_energy_ticker(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 82,
            "event_type": "other",
            "sentiment": "positive",
            "transmission_candidates": [],
        },
    )
    monkeypatch.setattr(
        mapper,
        "_build_ticker_pool_candidates",
        lambda semantic_output, subtype, sector_weight_view, sector_impacts: [
            {
                "symbol": "XOM",
                "sector": "Energy",
                "source_sector": "Energy",
                "source_theme": "integrated_oil",
                "confidence": 0.8,
                "whether_direct_ticker_mentioned": False,
                "reason": "seed",
            }
        ],
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-OTHER-002",
            "category": "X",
            "severity": "E2",
            "headline": "东京电子股价一度上涨6.2%",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 0.5}],
        }
    )
    rejected = out.data.get("stock_recommendation_buckets", {}).get("rejected", [])
    assert any(str(x.get("symbol", "")).upper() == "XOM" for x in rejected)


def test_non_us_market_context_blocks_us_energy_ticker(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 80,
            "event_type": "other",
            "sentiment": "neutral",
            "transmission_candidates": [],
        },
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-NONUS-001",
            "category": "X",
            "severity": "E2",
            "headline": "日本4月份制造业PMI回升至55.1",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 0.5}],
        }
    )
    symbols = [str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])]
    assert "XOM" not in symbols


def test_non_us_market_context_blocks_cat_proxy(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 80,
            "event_type": "other",
            "sentiment": "neutral",
            "transmission_candidates": [],
        },
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-NONUS-002",
            "category": "X",
            "severity": "E2",
            "headline": "日本开始额外投放国家石油储备",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "CAT", "sector": "Industrials", "industry": "Industrials", "change_pct": 0.5},
                {"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 0.5},
            ],
        }
    )
    symbols = [str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])]
    assert "CAT" not in symbols


def test_non_us_market_context_blocks_energy_service_proxies(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 80,
            "event_type": "other",
            "sentiment": "neutral",
            "transmission_candidates": [],
        },
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-NONUS-003",
            "category": "X",
            "severity": "E2",
            "headline": "欧洲央行官员称通胀上行风险加剧",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "SLB", "sector": "Energy", "industry": "Energy", "change_pct": 0.5},
                {"symbol": "HAL", "sector": "Energy", "industry": "Energy", "change_pct": 0.5},
                {"symbol": "BKR", "sector": "Energy", "industry": "Energy", "change_pct": 0.5},
            ],
        }
    )
    symbols = {str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])}
    assert "SLB" not in symbols
    assert "HAL" not in symbols
    assert "BKR" not in symbols


def test_non_us_market_context_does_not_leak_us_tech_fin_proxies(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 82,
            "event_type": "other",
            "sentiment": "neutral",
            "transmission_candidates": [],
        },
    )
    out = mapper.run(
        {
            "event_id": "ME-X-TEST-NONUS-004",
            "category": "X",
            "severity": "E2",
            "headline": "欧洲央行称经济增长面临短期逆风",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "NVDA", "sector": "Technology", "industry": "Technology", "change_pct": 0.5},
                {"symbol": "MSFT", "sector": "Technology", "industry": "Technology", "change_pct": 0.4},
                {"symbol": "JPM", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.2},
            ],
        }
    )
    symbols = {str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])}
    assert "NVDA" not in symbols
    assert "MSFT" not in symbols
    assert "JPM" not in symbols


def test_tier1_monetary_sector_impacts_non_empty(monkeypatch):
    """monetary 事件必须产生非空 sector_impacts（regression: S6-R017）。"""
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic, "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain", "confidence": 85,
            "event_type": "monetary", "sentiment": "positive",
        },
    )
    out = mapper.run({
        "event_id": "ME-T1-MON-001", "category": "E", "severity": "E2",
        "headline": "Fed signals rate cuts in September", "summary": "",
        "lifecycle_state": "Active",
        "sector_data": [{"sector": "Technology", "industry": "Technology"}],
    })
    assert out.status.value == "success"
    assert out.data.get("sector_impacts"), "monetary sector_impacts should not be empty"
    assert len(out.data["sector_impacts"]) > 0


def test_tier1_rate_hike_direction_not_uniform_benefit(monkeypatch):
    """rate_hike 场景不能被 uniform benefit 覆盖（regression: S6-R018）。"""
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic, "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain", "confidence": 85,
            "event_type": "monetary", "sentiment": "negative",
        },
    )
    out = mapper.run({
        "event_id": "ME-T1-RH-001", "category": "E", "severity": "E2",
        "headline": "Fed rate hike delivers hawkish surprise", "summary": "",
        "lifecycle_state": "Active",
        "sector_data": [{"sector": "Financial Services", "industry": "Financial Services"}],
    })
    directions = {imp.get("direction", "") for imp in out.data.get("sector_impacts", []) if imp.get("sector")}
    # At least one sector should not be "benefit" (carry original template direction, or watch)
    assert "watch" in directions or len(directions) > 1, \
        f"rate_hike directions should not all be benefit: {directions}"


def test_tier1_non_us_direct_mention_not_mistakenly_killed(monkeypatch):
    """non-US + direct mention 场景的 ticker 不被误杀（regression: S6-R019）。"""
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic, "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain", "confidence": 85,
            "event_type": "monetary", "sentiment": "positive",
        },
    )
    out = mapper.run({
        "event_id": "ME-T1-NONUS-001", "category": "E", "severity": "E2",
        "headline": "欧洲央行称经济增长面临短期逆风 提及会关注MSFT", "summary": "",
        "lifecycle_state": "Active",
        "sector_data": [
            {"symbol": "MSFT", "sector": "Technology", "industry": "Technology", "change_pct": 0.5},
        ],
    })
    symbols = {str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])}
    assert "MSFT" in symbols, "MSFT (direct mention in non-US context) should not be killed"


def test_tier1_regulatory_tech_no_conflict(monkeypatch):
    """regulatory/tech 不应同时出现在 Tier1 与 no-recommend 中（regression: S6-R020）。"""
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic, "analyze",
        lambda headline, summary: {
            "recommended_chain": "", "confidence": 80,
            "event_type": "regulatory", "sentiment": "neutral",
        },
    )
    out = mapper.run({
        "event_id": "ME-T1-REG-001", "category": "E", "severity": "E2",
        "headline": "SEC proposes new disclosure rules for ESG funds", "summary": "",
        "lifecycle_state": "Active",
        "sector_data": [{"sector": "Financial Services", "industry": "Financial Services"}],
    })
    assert out.status.value == "success"
    assert out.data.get("sector_impacts"), "regulatory sector_impacts should not be empty (Tier1 should cover it)"
    # Verify primary_sector is set (not rejected by no-recommend)
    assert out.data.get("primary_sector"), "regulatory should have primary_sector"
    # Verify stock recommendations are present (not blocked by watchlist)
    stock_buckets = out.data.get("stock_recommendation_buckets", {}) or {}
    has_candidates = bool(stock_buckets.get("candidates") or stock_buckets.get("recommended"))
    assert has_candidates, "regulatory should have stock candidates (not blocked by watchlist)"
