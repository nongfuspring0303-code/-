import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from conduction_mapper import ConductionMapper


def test_causal_contract_has_no_execution_suggestion_side_effects():
    out = ConductionMapper().run(
        {
            "event_id": "ME-CC-BOUNDARY-001",
            "category": "E",
            "severity": "E2",
            "headline": "Fed signals rate cuts ahead",
            "summary": "Policy easing expected",
            "lifecycle_state": "Active",
            "sector_data": [{"symbol": "XLK", "sector": "Technology", "industry": "Technology", "change_pct": 0.8}],
        }
    )
    data = out.data
    assert "trade_decision" not in data
    assert "execution_suggestion" not in data
    assert "final_action" not in data
