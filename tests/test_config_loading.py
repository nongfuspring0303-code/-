from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path):
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(payload, dict)
    return payload


def test_phase4_config_templates_exist():
    for name in [
        "event_to_shock.yaml",
        "factor_templates.yaml",
        "event_type_lv2_mapping.yaml",
        "backtest_protocol.yaml",
    ]:
        path = ROOT / "configs" / name
        assert path.exists(), f"missing config {name}"
        _load_yaml(path)


def test_factor_templates_contains_factors():
    payload = _load_yaml(ROOT / "configs" / "factor_templates.yaml")
    factors = payload.get("factors", [])
    assert len(factors) == 9
    for key in ["risk_appetite", "rates", "inflation", "growth", "usd", "liquidity", "volatility", "input_cost", "credit_stress"]:
        assert key in factors


def test_factor_templates_include_risk_off_template():
    payload = _load_yaml(ROOT / "configs" / "factor_templates.yaml")
    templates = payload.get("templates", {})
    assert "risk_off" in templates
    risk_off = templates["risk_off"]
    assert risk_off.get("risk_appetite", 0) < 0
    assert risk_off.get("volatility", 0) > 0


def test_gate_policy_has_no_stale_legacy_mapping_alias():
    payload = _load_yaml(ROOT / "configs" / "gate_policy.yaml")
    compatibility = payload.get("compatibility", {})
    assert "legacy_mapping_alias_name" not in compatibility
    assert "event_to_sector_mapping.yaml" not in (ROOT / "configs" / "gate_policy.yaml").read_text(encoding="utf-8")


def test_event_type_mapping_defaults():
    payload = _load_yaml(ROOT / "configs" / "event_type_lv2_mapping.yaml")
    defaults = payload.get("category_defaults", {})
    assert defaults.get("C", {}).get("lv2") == "tariff_shock"


def test_premium_stock_pool_metrics_are_consistent():
    payload = _load_yaml(ROOT / "configs" / "premium_stock_pool.yaml")
    stocks = payload.get("stocks", [])
    assert stocks, "premium_stock_pool must contain stocks"
    for stock in stocks:
        assert stock.get("roe_pct") is not None
        assert stock.get("roe") is not None
        assert stock.get("last_price") is not None
        assert stock.get("roe") == stock.get("roe_pct"), f"roe/roe_pct mismatch for {stock.get('symbol')}"
        assert stock.get("market_cap_billion") == stock.get("market_cap_usd_billion"), f"market cap mismatch for {stock.get('symbol')}"
