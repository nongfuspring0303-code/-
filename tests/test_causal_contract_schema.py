import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def test_causal_contract_schema_validation():
    schema_path = ROOT / "schemas" / "causal_contract.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    out = ConductionMapper().run(
        {
            "event_id": "ME-CC-SCHEMA-001",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [
                {"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 0.8},
            ],
        }
    )
    assert out.status.value == "success"
    jsonschema.validate(out.data["causal_contract"], schema)
