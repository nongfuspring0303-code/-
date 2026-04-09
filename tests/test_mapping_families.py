import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def test_mapping_contains_required_families():
    cfg_path = ROOT / "configs" / "conduction_chain.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    mapping_rules = cfg.get("event_to_chain_mapping", [])
    chains = {rule.get("chain_id") for rule in mapping_rules if isinstance(rule, dict)}
    required = {
        "liquidity_stress_chain",  # A
        "public_health_chain",  # B
        "geo_risk_chain",  # D
        "macro_data_chain",  # F
        "market_structure_chain",  # G
    }
    assert required.issubset(chains)


@pytest.mark.parametrize(
    "category,headline,summary,expected_chain",
    [
        ("A", "Bank run fears spread across regional lenders", "liquidity crisis risk", "template:liquidity_stress_chain"),
        ("B", "Public health emergency declared after new pandemic wave", "lockdown risk rises", "template:public_health_chain"),
        ("D", "War escalation triggers geopolitical risk premium", "sanctions likely", "template:geo_risk_chain"),
        ("F", "Nonfarm payroll misses expectations while CPI cools", "macro data surprise", "template:macro_data_chain"),
        ("G", "Market structure reform updates circuit breaker rules", "new trading regulation", "template:market_structure_chain"),
    ],
)
def test_family_samples_map_expected_chain(category, headline, summary, expected_chain):
    out = ConductionMapper().run(
        {
            "event_id": f"ME-{category}-TEST-001",
            "category": category,
            "severity": "E2",
            "headline": headline,
            "summary": summary,
            "lifecycle_state": "Active",
            "sector_data": [
                {"sector": "Technology", "industry": "Technology"},
                {"sector": "Financial Services", "industry": "Financial Services"},
                {"sector": "Healthcare", "industry": "Healthcare"},
                {"sector": "Energy", "industry": "Energy"},
                {"sector": "Industrials", "industry": "Industrials"},
            ],
        }
    )
    assert out.status.value == "success"
    assert out.data.get("mapping_source") == expected_chain
