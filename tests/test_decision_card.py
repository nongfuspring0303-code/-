import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from decision_card import DecisionCardGenerator


def test_decision_card_generate_and_get(tmp_path):
    gen = DecisionCardGenerator(archive_dir=str(tmp_path))
    card = gen.generate(
        trace_id="TRC-DC-1",
        event_id="EVT-1",
        summary="test summary",
        evidence=["e1"],
        counter_evidence=["c1"],
        risk_notes=["r1"],
        trigger_conditions=["t1"],
        invalid_conditions=["i1"],
    )

    loaded = gen.get_card(card.trace_id)
    assert loaded is not None
    assert loaded["trace_id"] == "TRC-DC-1"
    assert loaded["event_id"] == "EVT-1"
    assert loaded["summary"] == "test summary"


def test_decision_card_search_by_event_id(tmp_path):
    gen = DecisionCardGenerator(archive_dir=str(tmp_path))
    gen.generate("TRC-DC-2", "EVT-X", "s1")
    gen.generate("TRC-DC-3", "EVT-X", "s2")
    gen.generate("TRC-DC-4", "EVT-Y", "s3")

    cards = gen.search_by_event_id("EVT-X")
    assert len(cards) == 2
    assert {c["trace_id"] for c in cards} == {"TRC-DC-2", "TRC-DC-3"}
