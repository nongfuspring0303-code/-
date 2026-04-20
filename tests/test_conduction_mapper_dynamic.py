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

def test_conduction_mapper_filters_invalid_semantic_values(monkeypatch):
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
