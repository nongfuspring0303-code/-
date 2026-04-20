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
    assert out.data.get("audit", {}).get("ai_entity_stocks") == ["AAPL"]


def test_conduction_mapper_filters_non_ticker_entities(monkeypatch):
    """Non-ticker/symbol/stock entity types must be filtered out (T-002)."""
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": ["TSLA"],
            "entities": [
                {"type": "ticker", "value": "AAPL"},
                {"type": "company", "value": "Google"},
                {"type": "person", "value": "Jerome Powell"},
                {"type": "symbol", "value": "MSFT"},
            ],
            "transmission_candidates": [],
            "novelty_score": 0.3,
            "confidence": 60,
            "event_type": "tech",
            "sentiment": "positive",
        },
    )
    out = mapper.run({
        "event_id": "ME-E-TEST-008",
        "category": "E",
        "severity": "E2",
        "headline": "Tech sector update",
        "summary": "",
        "lifecycle_state": "Active",
        "sector_data": [{"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 0.5}],
    })
    assert out.status.value == "success"
    entity_stocks = out.data.get("audit", {}).get("ai_entity_stocks", [])
    assert "AAPL" in entity_stocks
    assert "MSFT" in entity_stocks
    assert "Google" not in str(entity_stocks)
    assert "Jerome Powell" not in str(entity_stocks)
    symbols = [str(x.get("symbol", "")).upper() for x in out.data.get("stock_candidates", [])]
    assert "TSLA" in symbols
    assert "AAPL" in symbols
    assert "MSFT" in symbols


def test_conduction_mapper_neutral_sentiment_fallback_is_watch(monkeypatch):
    """Neutral sentiment must map to 'watch' direction, not 'hurt' (T-003, BLOCKER fix verification)."""
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": ["SPY"],
            "entities": [],
            "transmission_candidates": [],
            "novelty_score": 0.1,
            "confidence": 40,
            "event_type": "other",
            "sentiment": "neutral",
            "verdict": "hit",
        },
    )
    monkeypatch.setattr(mapper.shock_classifier, "classify", lambda category=None, headline=None, summary=None, severity=None: {
        "category": "E",
        "event_type_lv1": "other",
        "event_type_lv2": None,
        "classification_confidence": 30,
        "market_impact_confidence": 20,
        "shock_profile": None,
    })
    def mock_match_chain_template(category, headline, summary, semantic_output=None):
        return None
    monkeypatch.setattr(mapper, "_match_chain_template", mock_match_chain_template)

    out = mapper.run({
        "event_id": "ME-E-TEST-009",
        "category": "X",
        "severity": "E3",
        "headline": "Mixed economic data released",
        "summary": "No clear direction",
        "lifecycle_state": "Active",
        "sector_data": [],
    })
    assert out.status.value == "success"
    sector_impacts = out.data.get("sector_impacts", [])
    assert len(sector_impacts) == 1
    assert sector_impacts[0]["direction"] == "watch", (
        f"Neutral sentiment should map to 'watch', got '{sector_impacts[0]['direction']}'"
    )
    candidates = out.data.get("stock_candidates", [])
    assert len(candidates) == 1
    assert candidates[0]["direction"] == "watch", (
        f"Neutral stock candidate direction should be 'watch', got '{candidates[0]['direction']}'"
    )


def test_conduction_mapper_semantic_candidates_priority_over_rule(monkeypatch):
    """Semantic candidates should appear before rule-based candidates (T-004)."""
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain",
            "recommended_stocks": ["NVDA", "AAPL"],
            "entities": [{"type": "ticker", "value": "AAPL"}],
            "transmission_candidates": ["risk_appetite"],
            "novelty_score": 0.5,
            "confidence": 80,
            "event_type": "monetary",
            "sentiment": "positive",
        },
    )
    out = mapper.run({
        "event_id": "ME-E-TEST-010",
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
    sources = [str(x.get("source", "")) for x in candidates]
    assert "semantic" in sources


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
