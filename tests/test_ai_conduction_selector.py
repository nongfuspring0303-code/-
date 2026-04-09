import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ai_conduction_selector import AIConductionSelector


def test_selector_prefers_semantic_when_confidence_high():
    selector = AIConductionSelector(min_confidence=70)
    out = selector.choose_chain(
        {
            "recommended_chain": "trade_talks_chain",
            "confidence": 85,
        },
        "tariff_chain",
    )
    assert out["chain_id"] == "trade_talks_chain"
    assert out["selection_source"] == "semantic"


def test_selector_falls_back_to_rules_when_semantic_low_confidence():
    selector = AIConductionSelector(min_confidence=70)
    out = selector.choose_chain(
        {
            "recommended_chain": "trade_talks_chain",
            "confidence": 40,
        },
        "tariff_chain",
    )
    assert out["chain_id"] == "tariff_chain"
    assert out["selection_source"] == "rules"


def test_selector_handles_non_numeric_confidence_safely():
    selector = AIConductionSelector(min_confidence=70)
    out = selector.choose_chain(
        {
            "recommended_chain": "trade_talks_chain",
            "confidence": "85%",
        },
        "tariff_chain",
    )
    assert out["chain_id"] == "tariff_chain"
    assert out["selection_source"] == "rules"
