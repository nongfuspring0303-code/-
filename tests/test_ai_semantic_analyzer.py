import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ai_semantic_analyzer import SemanticAnalyzer


def test_semantic_analyzer_outputs_required_fields_when_disabled(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("modules: {}\nruntime:\n  semantic:\n    enabled: false\n", encoding="utf-8")
    out = SemanticAnalyzer(config_path=str(cfg)).analyze("headline", "")
    assert {"event_type", "sentiment", "confidence", "recommended_chain"} <= set(out.keys())
    assert out["fallback_reason"] == "semantic_disabled"


def test_semantic_analyzer_detects_trade_meeting(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 70\n", encoding="utf-8")
    out = SemanticAnalyzer(config_path=str(cfg)).analyze("Trump-Xi trade meeting", "capital flows")
    assert out["event_type"] == "trade_talks"
    assert out["recommended_chain"] == "trade_talks_chain"
    assert out["sentiment"] == "neutral"
