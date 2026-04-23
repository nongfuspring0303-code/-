import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper
from opportunity_score import OpportunityScorer


def _sector_whitelist() -> set[str]:
    cfg = yaml.safe_load((ROOT / "configs" / "sector_impact_mapping.yaml").read_text(encoding="utf-8")) or {}
    whitelist: set[str] = set()
    for item in cfg.get("mappings", []) or []:
        if isinstance(item, dict):
            sector = str(item.get("sector", "")).strip()
            if sector:
                whitelist.add(sector)
    mapping = cfg.get("mapping", {})
    if isinstance(mapping, dict):
        for values in mapping.values():
            if isinstance(values, list):
                for sector in values:
                    sector_name = str(sector or "").strip()
                    if sector_name:
                        whitelist.add(sector_name)
    return whitelist


def test_stage3b_sectors_final_output_whitelist_only():
    out = ConductionMapper().run(
        {
            "event_id": "ME-B-S3B-001",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.8},
                {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 1.2},
            ],
        }
    )

    whitelist = _sector_whitelist()
    sectors = {str(item.get("sector", "")).strip() for item in out.data.get("sector_impacts", [])}

    assert sectors
    assert sectors.issubset(whitelist)


def test_stage3b_policy_mapping_prefers_canonical_sector_field():
    out = ConductionMapper().run(
        {
            "event_id": "ME-B-S3B-001B",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLF", "sector": "Financials", "industry": "金融", "change_pct": 0.8},
            ],
        }
    )

    sectors = {str(item.get("sector", "")).strip() for item in out.data.get("sector_impacts", [])}
    symbols = {str(item.get("symbol", "")).strip().upper() for item in out.data.get("stock_candidates", [])}

    assert "Financial Services" in sectors
    assert "XLF" in symbols
    assert out.data.get("needs_manual_review") is False


def test_stage3b_sector_normalization_is_case_insensitive():
    mapper = ConductionMapper()

    assert mapper._normalize_sector_name("Financials") == "Financial Services"  # noqa: SLF001
    assert mapper._normalize_sector_name("financials") == "Financial Services"  # noqa: SLF001
    assert mapper._normalize_sector_name("FINANCIALS") == "Financial Services"  # noqa: SLF001


def test_stage3b_ticker_pool_requires_truth_source():
    scorer = OpportunityScorer()
    known = scorer.build_opportunity_update(
        {
            "trace_id": "evt_s3b_energy",
            "schema_version": "v1.0",
            "sectors": [{"name": "Energy", "direction": "LONG", "impact_score": 0.8, "confidence": 0.8}],
            "stock_candidates": [],
        }
    )
    unknown = scorer.build_opportunity_update(
        {
            "trace_id": "evt_s3b_unknown",
            "schema_version": "v1.0",
            "sectors": [{"name": "Unmapped Sector", "direction": "LONG", "impact_score": 0.8, "confidence": 0.8}],
            "stock_candidates": [],
        }
    )

    pool_symbols = set(scorer.pool._stocks_by_symbol.keys())  # noqa: SLF001
    known_symbols = {str(item.get("symbol", "")).strip().upper() for item in known.get("opportunities", [])}

    assert known_symbols
    assert known_symbols.issubset(pool_symbols)
    assert unknown.get("opportunities") == []


def test_stage3b_financial_jpm_fallback_removed():
    out = ConductionMapper().run(
        {
            "event_id": "ME-B-S3B-003",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [],
        }
    )

    symbols = {str(item.get("symbol", "")).strip().upper() for item in out.data.get("stock_candidates", [])}
    sectors = {str(item.get("sector", "")).strip() for item in out.data.get("sector_impacts", [])}

    assert "JPM" not in symbols
    assert "SPY" not in symbols
    assert "Financial Services" not in sectors
    assert out.data.get("needs_manual_review") is True


def test_stage3b_placeholder_leakage_under_1_percent(monkeypatch):
    mapper = ConductionMapper()
    monkeypatch.setattr(
        mapper.semantic,
        "analyze",
        lambda headline, summary: {
            "recommended_chain": "rate_cut_chain",
            "recommended_stocks": ["", None, "nvda", "N/A", 123, "aapl", "NVDA"],
            "entities": [
                {"type": "ticker", "value": ""},
                {"type": "symbol", "value": None},
                {"type": "ticker", "value": "AAPL"},
            ],
            "transmission_candidates": ["risk_appetite"],
            "novelty_score": 0.5,
            "confidence": 80,
            "event_type": "monetary",
            "sentiment": "positive",
        },
    )

    out = mapper.run(
        {
            "event_id": "ME-B-S3B-004",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.8},
                {"symbol": "XLF", "sector": "Financial Services", "industry": "Financial Services", "change_pct": 0.8},
            ],
        }
    )

    symbols = [str(item.get("symbol", "")).strip().upper() for item in out.data.get("stock_candidates", [])]
    invalid = [symbol for symbol in symbols if not symbol or symbol in {"N/A", "NONE"}]
    leak_rate = len(invalid) / max(len(symbols), 1)

    assert leak_rate <= 0.01
    assert "" not in symbols
    assert "N/A" not in symbols
    assert "NONE" not in symbols


def test_stage3b_template_collapse_does_not_promote_failure_path():
    out = ConductionMapper().run(
        {
            "event_id": "ME-B-S3B-005",
            "category": "Z",
            "severity": "E2",
            "headline": "Ambiguous event without asset clue",
            "summary": "No clear sector or ticker signal",
            "lifecycle_state": "Active",
            "sector_data": [],
        }
    )

    assert out.status.value == "success"
    assert out.data.get("mapping_source") == "rule"
    assert out.data.get("needs_manual_review") is True
    assert out.data.get("sector_impacts") == []
    assert out.data.get("stock_candidates") == []
