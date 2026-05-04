from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def test_guardrails_thresholds_from_config():
    mapper = ConductionMapper()
    mapper._tier1_guardrails = {
        "tier1_event_types": ["energy"],
        "recommendation_thresholds": {
            "recommended_min_confidence": 0.83,
            "watchlist_min_confidence": 0.55,
        },
    }
    mapper._apply_guardrails_config()
    assert mapper._RECOMMENDED_MIN_CONFIDENCE == 0.83
    assert mapper._WATCHLIST_MIN_CONFIDENCE == 0.55


def test_guardrails_blocklists_from_config():
    mapper = ConductionMapper()
    mapper._tier1_guardrails = {
        "tier1_event_types": ["energy"],
        "proxy_blocklists": {
            "energy_tickers": ["AAA", "BBB"],
            "non_us_block_proxy_tickers": ["CCC"],
            "us_tech_fin_proxy_tickers": ["DDD"],
        },
        "market_hints": {
            "non_us": ["测试非美"],
            "geo_energy_allowed": ["测试能源允许"],
        },
    }
    mapper._apply_guardrails_config()
    assert mapper._ENERGY_TICKERS == {"AAA", "BBB"}
    assert mapper._NON_US_BLOCK_PROXY_TICKERS == {"CCC"}
    assert mapper._US_TECH_FIN_PROXY_TICKERS == {"DDD"}
    assert mapper._NON_US_MARKET_HINTS == ("测试非美",)
    assert mapper._GEO_ENERGY_ALLOWED_HINTS == ("测试能源允许",)


def test_guardrails_missing_config_enters_safe_fallback():
    mapper = ConductionMapper()
    mapper._tier1_guardrails = {}
    mapper._apply_guardrails_config()
    assert mapper._TIER1_EVENT_TYPES == set()
    assert mapper._RECOMMENDED_MIN_CONFIDENCE > 1.0
    assert mapper._ENERGY_TICKERS == set()


def test_guardrails_invalid_threshold_type_falls_back_safe():
    mapper = ConductionMapper()
    mapper._tier1_guardrails = {
        "tier1_event_types": ["energy"],
        "recommendation_thresholds": "invalid",
    }
    mapper._apply_guardrails_config()
    assert mapper._RECOMMENDED_MIN_CONFIDENCE > 1.0
    assert mapper._WATCHLIST_MIN_CONFIDENCE == 0.50
