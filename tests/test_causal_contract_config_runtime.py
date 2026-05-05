import json
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def test_pr110_runtime_uses_causal_contract_policy_single_source():
    mapper = ConductionMapper()
    cfg = mapper._pr110_contract_cfg()
    assert cfg.get("schema_version") == "stage6.causal_contract_policy.v1"
    assert "expectation_gap" in cfg
    assert "market_validation" in cfg
    assert "dominant_driver" in cfg
    tier1_rules = yaml.safe_load((ROOT / "configs" / "tier1_mapping_rules.yaml").read_text(encoding="utf-8"))
    assert "pr110_min_contract" not in (tier1_rules or {})


def test_schema_enums_align_with_policy():
    policy = yaml.safe_load((ROOT / "configs" / "causal_contract_policy.yaml").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas" / "causal_contract.schema.json").read_text(encoding="utf-8"))

    assert schema["properties"]["expectation_gap"]["properties"]["value"]["enum"] == policy["expectation_gap"]["allowed_values"]
    assert schema["properties"]["relative_direction"]["enum"] == policy["relative_direction"]["allowed_values"]
    assert schema["properties"]["absolute_direction"]["enum"] == policy["absolute_direction"]["allowed_values"]
    assert schema["properties"]["dominant_driver"]["properties"]["primary"]["enum"] == policy["dominant_driver"]["allowed_values"]
    assert schema["properties"]["dominant_driver"]["properties"]["secondary"]["items"]["enum"] == policy["dominant_driver"]["allowed_values"]
    assert schema["properties"]["macro_factor"]["properties"]["factor"]["enum"] == policy["macro_factor"]["factor_allowed_values"]
    assert schema["properties"]["macro_factor"]["properties"]["direction"]["enum"] == policy["macro_factor"]["direction_allowed_values"]
    assert schema["properties"]["macro_factor"]["properties"]["strength"]["enum"] == policy["macro_factor"]["strength_allowed_values"]
    assert schema["properties"]["market_validation"]["properties"]["status"]["enum"] == policy["market_validation"]["allowed_status"]
    ev = schema["properties"]["market_validation"]["properties"]["evidence"]["items"]["properties"]
    assert ev["expected"]["enum"] == policy["market_validation"]["evidence"]["expected_values"]
    assert ev["observed"]["enum"] == policy["market_validation"]["evidence"]["observed_values"]
    assert ev["layer"]["enum"] == policy["market_validation"]["evidence"]["layer_values"]
    assert schema["properties"]["impact_layers"]["items"]["enum"] == policy["impact_layers"]["allowed_values"]


def test_causal_contract_schema_still_validates_runtime_output():
    schema = json.loads((ROOT / "schemas" / "causal_contract.schema.json").read_text(encoding="utf-8"))
    out = ConductionMapper().run(
        {
            "event_id": "ME-CC-POLICY-001",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 0.8}],
        }
    )
    jsonschema.validate(out.data["causal_contract"], schema)
