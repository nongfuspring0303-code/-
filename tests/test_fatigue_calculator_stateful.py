import os
import tempfile
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fatigue_calculator import FatigueCalculator
from state_store import EventStateStore


def test_fatigue_calculator_reads_category_from_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "event_states.db")
        store = EventStateStore(db_path=db_path)
        for idx in range(3):
            store.upsert_state(
                f"evt_c_{idx}",
                {
                    "internal_state": "Active",
                    "lifecycle_state": "Active",
                    "catalyst_state": "first_impulse",
                    "retry_count": idx,
                    "metadata": {
                        "category": "C",
                        "narrative_tags": ["trade_war"],
                    },
                },
            )
        store.upsert_state(
            "evt_e_1",
            {
                "internal_state": "Active",
                "lifecycle_state": "Active",
                "catalyst_state": "first_impulse",
                "retry_count": 0,
                "metadata": {
                    "category": "E",
                    "narrative_tags": ["policy_pivot"],
                },
            },
        )

        out = FatigueCalculator(state_store=store).run(
            {
                "event_id": "evt_query",
                "category": "C",
                "lifecycle_state": "Active",
                "narrative_tags": ["trade_war"],
                "days_since_last_dead": 5,
            }
        )

        assert out.status.value == "success"
        assert out.data["fatigue_category"] == 20
        assert out.data["fatigue_tag"] == 20
        assert out.data["fatigue_final"] == 20
