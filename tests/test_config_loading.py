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


def test_event_type_mapping_defaults():
    payload = _load_yaml(ROOT / "configs" / "event_type_lv2_mapping.yaml")
    defaults = payload.get("category_defaults", {})
    assert defaults.get("C", {}).get("lv2") == "tariff_shock"
