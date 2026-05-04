from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent


def test_tier1_mapping_rules_contract():
    path = ROOT / "configs" / "tier1_mapping_rules.yaml"
    assert path.exists(), f"missing file: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    assert data.get("schema_version"), "schema_version is required"
    assert data.get("version"), "version is required"

    tier1_types = data.get("tier1_event_types", [])
    assert isinstance(tier1_types, list) and tier1_types, "tier1_event_types must be a non-empty list"
    assert len(tier1_types) == 10, f"expected 10 tier1 types, got {len(tier1_types)}"

    base = data.get("base_sector_weights", {})
    assert isinstance(base, dict) and base, "base_sector_weights must be a non-empty dict"
    for t in tier1_types:
        assert t in base, f"base_sector_weights missing tier1 type: {t}"
        assert isinstance(base[t], dict) and base[t], f"base_sector_weights[{t}] must be non-empty dict"

    subtype_rules = data.get("subtype_rules", {})
    assert isinstance(subtype_rules, dict), "subtype_rules must be a dict"

    ticker_pool = data.get("ticker_pool", {})
    assert isinstance(ticker_pool, dict) and ticker_pool, "ticker_pool must be a non-empty dict"

    guardrails = data.get("recommendation_guardrails", {})
    assert isinstance(guardrails, dict) and guardrails, "recommendation_guardrails must exist"

    thresholds = guardrails.get("recommendation_thresholds", {})
    assert isinstance(thresholds, dict) and thresholds, "recommendation_thresholds must exist"
    for key in ("recommended_min_confidence", "watchlist_min_confidence"):
        value = thresholds.get(key)
        assert isinstance(value, (int, float)), f"{key} must be numeric"

    blocklists = guardrails.get("proxy_blocklists", {})
    assert isinstance(blocklists, dict) and blocklists, "proxy_blocklists must exist"
    for k, v in blocklists.items():
        assert isinstance(v, list), f"proxy_blocklists.{k} must be list"

    hints = guardrails.get("market_hints", {})
    assert isinstance(hints, dict) and hints, "market_hints must exist"
    for k, v in hints.items():
        assert isinstance(v, list), f"market_hints.{k} must be list"
