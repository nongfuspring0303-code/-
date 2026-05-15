import logging

import pytest
import yaml

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def test_empty_headline_and_summary_short_circuit_before_expensive_steps(monkeypatch):
    mapper = ConductionMapper()

    monkeypatch.setattr(
        mapper.shock_classifier,
        "classify",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("classify should not run on empty text")),
    )
    monkeypatch.setattr(
        mapper.factor_vectorizer,
        "vectorize",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("vectorize should not run on empty text")),
    )
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("semantic should not run on empty text")),
    )

    out = mapper.run(
        {
            "event_id": "ME-AUDIT-3-001",
            "category": "X",
            "severity": "E2",
            "headline": "",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [],
        }
    )

    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "INSUFFICIENT_EVENT_CONTEXT"


def test_tier1_override_records_audit_and_provenance(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "confidence": 82,
            "event_type": "commodity",
            "sentiment": "positive",
            "transmission_candidates": ["gold rally"],
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-AUDIT-3-002",
            "category": "X",
            "severity": "E2",
            "headline": "Gold surges as commodity market rallies",
            "summary": "gold and miners rally",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "NEM", "sector": "Materials", "industry": "Materials", "change_pct": 1.2},
                {"symbol": "XOM", "sector": "Energy", "industry": "Energy", "change_pct": 0.8},
            ],
        }
    )

    assert out.status.value == "success"
    audit = out.data.get("audit", {})
    override = audit.get("tier1_sector_override", {})
    assert override.get("override_reason") == "tier1_weighted_sector_override"
    assert override.get("dropped_count", 0) >= 1
    assert override.get("provenance")
    assert override.get("retained_count", 0) == len(out.data.get("sector_impacts", []))
    assert all(impact.get("driver_type") == "tier1_weight" for impact in out.data.get("sector_impacts", []))
    assert "final_recommended_stocks" not in out.data


def test_confidence_normalization_accepts_fraction_and_percent_inputs():
    mapper = ConductionMapper()
    assert mapper._normalize_confidence_value(0.82) == pytest.approx(0.82)
    assert mapper._normalize_confidence_value(82) == pytest.approx(0.82)

    sector_weight_view = {
        "sector_weights": {"Technology": 0.50},
        "primary_sector": "Technology",
        "secondary_sectors": [],
    }
    sector_impacts = [{"sector": "Technology", "direction": "benefit"}]

    fraction_candidates = mapper._build_ticker_pool_candidates(
        {"confidence": 0.82, "recommended_stocks": [], "entities": []},
        "rate_cut",
        sector_weight_view,
        sector_impacts,
    )
    percent_candidates = mapper._build_ticker_pool_candidates(
        {"confidence": 82, "recommended_stocks": [], "entities": []},
        "rate_cut",
        sector_weight_view,
        sector_impacts,
    )

    assert fraction_candidates
    assert percent_candidates
    assert fraction_candidates[0]["confidence"] == percent_candidates[0]["confidence"]


def test_company_alias_entity_resolves_into_semantic_candidates(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [{"type": "company", "value": "Google"}],
            "confidence": 88,
            "event_type": "monetary",
            "sentiment": "positive",
            "transmission_candidates": [],
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-AUDIT-3-003",
            "category": "X",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "GOOGL", "sector": "Technology", "industry": "Technology", "change_pct": 1.0},
                {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.4},
            ],
        }
    )

    assert out.status.value == "success"
    symbols = {str(item.get("symbol", "")).upper() for item in out.data.get("stock_candidates", [])}
    assert "GOOGL" in symbols
    assert "final_recommended_stocks" not in out.data
    assert "execution" not in out.data
    assert "broker" not in out.data
    assert "final_action" not in out.data


def test_none_sector_and_template_values_are_safely_ignored():
    mapper = ConductionMapper()
    assert mapper._resolve_sector_snapshot_name({"sector": None, "industry": None}) == ""
    assert mapper._normalize_sector_name(None) == ""

    template_mapping = mapper._build_template_mapping({"id": None, "name": None, "levels": []}, [])
    assert template_mapping["mapping_source"] == "template:unknown"
    assert template_mapping["conduction_path"] == ["模板链路"]


def test_candidate_filtering_adds_drop_diagnostics(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "",
            "recommended_stocks": [],
            "entities": [],
            "confidence": 80,
            "event_type": "monetary",
            "sentiment": "neutral",
            "transmission_candidates": [],
        },
    )
    monkeypatch.setattr(
        mapper,
        "_build_ticker_pool_candidates",
        lambda semantic_output, subtype, sector_weight_view, sector_impacts: [
            {
                "symbol": "NVDA",
                "sector": "Technology",
                "direction": "watch",
                "reason": "seed",
                "source": "tier1_ticker_pool",
                "confidence": 0.10,
                "whether_direct_ticker_mentioned": False,
            }
        ],
    )

    out = mapper.run(
        {
            "event_id": "ME-AUDIT-3-004",
            "category": "X",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "NVDA", "sector": "Technology", "industry": "Technology", "change_pct": 0.5},
            ],
        }
    )

    buckets = out.data.get("stock_recommendation_buckets", {})
    assert buckets.get("drop_diagnostics")
    assert buckets.get("rejected")
    assert buckets["rejected"][0].get("drop_reason") == "low_confidence"
    assert buckets["rejected"][0].get("drop_diagnostics", {}).get("semantic_event_type") == "monetary"


def test_duplicate_template_ids_emit_warning(tmp_path, caplog):
    mapper = ConductionMapper()
    cfg = {
        "chain_templates": [
            {
                "id": "custom_chain",
                "name": "custom",
                "levels": [
                    {"level": "macro", "name": "macro", "factors": []},
                    {"level": "sector", "name": "sector", "sectors": [{"name": "Technology", "direction": "benefit", "impact_score": 1.0}]},
                ],
            },
            {
                "id": "custom_chain",
                "name": "custom-duplicate",
                "levels": [
                    {"level": "macro", "name": "macro", "factors": []},
                    {"level": "sector", "name": "sector", "sectors": [{"name": "Technology", "direction": "benefit", "impact_score": 1.0}]},
                ],
            },
        ],
        "event_to_chain_mapping": [
            {"event_keywords": ["custom trigger"], "chain_id": "custom_chain"}
        ],
    }
    path = tmp_path / "conduction_chain.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    mapper.chain_config_path = path
    mapper.config_center.register("conduction_chain", path)

    caplog.set_level(logging.WARNING)
    out = mapper.run(
        {
            "event_id": "ME-AUDIT-3-005",
            "category": "X",
            "severity": "E2",
            "headline": "custom trigger event",
            "summary": "",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "NVDA", "sector": "Technology", "industry": "Technology", "change_pct": 0.5},
            ],
        }
    )

    assert out.status.value == "success"
    assert out.data["mapping_source"] == "template:custom_chain"
    assert any("duplicate chain template ids detected" in record.message for record in caplog.records)
