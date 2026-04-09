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
