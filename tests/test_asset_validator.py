import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transmission_engine.core.asset_validator import AssetValidator


def _base_input(**overrides):
    payload = {
        "event_id": "ME-B-AV-001",
        "schema_version": "v1.1",
        "raw_macro_factor_vector": {
            "risk_appetite": 35,
            "rates": 28,
            "inflation": 24,
            "growth": 30,
            "usd": 16,
            "liquidity": 22,
            "volatility": 12,
            "input_cost": 18,
            "credit_stress": 8,
        },
    }
    payload.update(overrides)
    return payload


def test_asset_validator_emits_required_fields_and_two_decimal_scores():
    out = AssetValidator().run(_base_input())

    assert out.status.value == "success"
    asset_validation = out.data["asset_validation"]
    assert {"score", "status", "leaders", "divergences", "basket_scores"}.issubset(asset_validation.keys())
    assert len(asset_validation["leaders"]) >= 1
    assert all(isinstance(item, str) and item for item in asset_validation["leaders"])
    assert asset_validation["score"] == round(asset_validation["score"], 2)
    assert all(value == round(value, 2) for value in asset_validation["basket_scores"].values())
    assert all(value == round(value, 2) for value in out.data["macro_factor_vector"].values())


def test_asset_validator_uses_whitelist_and_notes_for_non_whitelist_assets():
    out = AssetValidator().run(
        _base_input(
            candidate_assets=[
                {"symbol": "US Equities"},
                {"symbol": "Ethereum"},
                {"symbol": "BTC"},
            ]
        )
    )

    assert "Ignored non-whitelist asset: Ethereum" in out.data["notes"]
    assert all(item != "Ethereum" for item in out.data["asset_validation"]["leaders"])
    assert all(item != "Ethereum" for item in out.data["asset_validation"]["divergences"])


def test_asset_validator_applies_conflict_penalty_when_divergences_exceed_two():
    out = AssetValidator().run(
        _base_input(
            raw_macro_factor_vector={
                "risk_appetite": -42,
                "rates": -30,
                "inflation": -18,
                "growth": -36,
                "usd": 8,
                "liquidity": -24,
                "volatility": 28,
                "input_cost": -12,
                "credit_stress": 30,
            }
        )
    )

    asset_validation = out.data["asset_validation"]
    assert len(asset_validation["divergences"]) > 2
    assert asset_validation["score"] < 65


def test_asset_validator_supports_three_state_output():
    strong = AssetValidator().run(
        _base_input(
            raw_macro_factor_vector={
                "risk_appetite": 72,
                "rates": 64,
                "inflation": 58,
                "growth": 70,
                "usd": 26,
                "liquidity": 44,
                "volatility": 18,
                "input_cost": 36,
                "credit_stress": 10,
            }
        )
    )
    middle = AssetValidator().run(
        _base_input(
            raw_macro_factor_vector={
                "risk_appetite": 14,
                "rates": 12,
                "inflation": 10,
                "growth": 18,
                "usd": 6,
                "liquidity": 10,
                "volatility": 8,
                "input_cost": 8,
                "credit_stress": 4,
            }
        )
    )
    weak = AssetValidator().run(
        _base_input(
            raw_macro_factor_vector={
                "risk_appetite": -28,
                "rates": -18,
                "inflation": -12,
                "growth": -20,
                "usd": -6,
                "liquidity": -14,
                "volatility": 24,
                "input_cost": -8,
                "credit_stress": 16,
            }
        )
    )

    assert strong.data["asset_validation"]["status"] == "confirmed"
    assert middle.data["asset_validation"]["status"] == "divergent"
    assert weak.data["asset_validation"]["status"] == "unconfirmed"


def test_asset_baskets_config_contains_five_baskets_and_whitelist():
    cfg = yaml.safe_load((ROOT / "configs" / "asset_baskets.yaml").read_text(encoding="utf-8"))
    baskets = cfg["asset_baskets"]
    whitelist = cfg["asset_universe"]["whitelist"]

    assert list(baskets.keys()) == [
        "rates_basket",
        "risk_off_basket",
        "commodity_basket",
        "usd_basket",
        "growth_vs_value_basket",
    ]
    assert len(whitelist) >= 1
