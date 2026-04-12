import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import intel_modules
from intel_modules import EventCapture, EventObjectifier, IntelPipeline, SeverityEstimator, SourceRankerModule


def _raw_event():
    return {
        "headline": "Fed announces emergency liquidity action after tariff shock",
        "source": "https://www.reuters.com/markets/us/example",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 31,
        "vix_change_pct": 32,
        "spx_move_pct": 2.1,
        "sector_move_pct": 4.0,
        "sequence": 2,
    }


def test_event_capture_detects_keyword():
    out = EventCapture().run(_raw_event())
    assert out.status.value == "success"
    assert out.data["captured"] is True


def test_event_capture_with_ai_analysis():
    payload = {
        "headline": "Company reports higher trade volume on earnings day",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }
    out = EventCapture().run(payload)
    assert out.status.value == "success"
    # New behavior: all news go through AI analysis
    # captured depends on AI confidence + optional keyword bonus
    assert "ai_confidence" in out.data


def test_event_capture_classifies_trade_war_as_tariff():
    payload = {
        "headline": "Trade war escalates after new tariffs",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }
    out = EventCapture().run(payload)
    assert out.status.value == "success"
    assert out.data["captured"] is True
    assert out.data["category_hint"] == "C"


def test_event_capture_keyword_miss_can_use_ai_hit(monkeypatch):
    payload = {
        "headline": "Committee confirms closed-door policy dialogue",
        "raw_text": "Delegates launch trade meeting on tariff framework",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }
    capture = EventCapture()

    def _fake_ai(_headline, _raw_text):
        return {"verdict": "hit", "confidence": 82, "reason": "semantic match"}

    monkeypatch.setattr(capture.semantic, "analyze", _fake_ai)
    out = capture.run(payload)

    assert out.status.value == "success"
    assert out.data["captured"] is True
    assert out.data["capture_source"] == "ai"
    assert out.data["ai_verdict"] == "hit"
    assert out.data["ai_confidence"] == 82
    assert out.data["ai_reason"] == "ai(semantic match)"


def test_event_capture_keyword_hit_keeps_rules_source_without_ai(monkeypatch):
    payload = {
        "headline": "Fed signals liquidity support measures",
        "raw_text": "",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }
    capture = EventCapture()

    def _fake_ai_success(_headline, _raw_text):
        return {"verdict": "abstain", "confidence": 35, "reason": "not relevant", "event_type": "unknown", "sentiment": "neutral"}

    monkeypatch.setattr(capture.semantic, "analyze", _fake_ai_success)
    out = capture.run(payload)

    assert out.status.value == "success"
    assert out.data["captured"] is True
    assert out.data["ai_verdict"] == "abstain"
    assert out.data["ai_confidence"] == 45


def test_event_capture_keyword_miss_and_ai_miss_returns_none_source(monkeypatch):
    payload = {
        "headline": "Company opens a new regional office",
        "raw_text": "Quarterly planning update",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }
    capture = EventCapture()

    def _fake_ai(_headline, _raw_text):
        return {"verdict": "abstain", "confidence": 40, "reason": "not relevant"}

    monkeypatch.setattr(capture.semantic, "analyze", _fake_ai)
    out = capture.run(payload)

    assert out.status.value == "success"
    assert out.data["captured"] is False
    assert out.data["capture_source"] == "none"
    assert out.data["ai_verdict"] == "abstain"
    assert out.data["ai_confidence"] == 40
    assert out.data["ai_reason"] == "ai(not relevant)"


def test_event_capture_keyword_miss_ai_hit_below_threshold_stays_none(monkeypatch):
    payload = {
        "headline": "Committee confirms closed-door policy dialogue",
        "raw_text": "Delegates launch trade meeting on tariff framework",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }
    capture = EventCapture()

    def _fake_ai(_headline, _raw_text):
        return {"verdict": "hit", "confidence": 69, "reason": "weak semantic match"}

    monkeypatch.setattr(capture.semantic, "analyze", _fake_ai)
    out = capture.run(payload)

    assert out.status.value == "success"
    assert out.data["captured"] is False
    assert out.data["capture_source"] == "none"
    assert out.data["ai_verdict"] == "hit"
    assert out.data["ai_confidence"] == 69
    assert out.data["ai_reason"] == "ai(weak semantic match)"


def test_event_capture_semantic_init_failure_degrades_gracefully(monkeypatch):
    class _BrokenSemantic:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("init failed")

    payload = {
        "headline": "Company updates office policy memo",
        "raw_text": "Routine internal update",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }

    monkeypatch.setattr(intel_modules, "SemanticAnalyzer", _BrokenSemantic)
    capture = EventCapture()
    out = capture.run(payload)

    assert out.status.value == "success"
    assert out.data["captured"] is False
    assert out.data["capture_source"] == "none"
    assert out.data["ai_verdict"] == "keyword_fallback"
    assert "keyword_fallback" in out.data["ai_reason"]


def test_event_capture_semantic_runtime_exception_fallback(monkeypatch):
    payload = {
        "headline": "Committee confirms closed-door policy dialogue",
        "raw_text": "No direct keyword match in configured capture set",
        "source": "https://example.com",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 10,
        "sequence": 1,
    }
    capture = EventCapture()

    def _raise_runtime(_headline, _raw_text):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(capture.semantic, "analyze", _raise_runtime)
    out = capture.run(payload)

    assert out.status.value == "success"
    assert out.data["captured"] is False
    assert out.data["capture_source"] == "none"
    assert out.data["ai_verdict"] == "keyword_fallback"
    assert "keyword_fallback" in out.data["ai_reason"]


def test_source_ranker_b_rank():
    out = SourceRankerModule().run({"source_url": "https://www.reuters.com/markets/us/example"})
    assert out.data["rank"] == "B"


def test_source_ranker_rejects_substring_spoof_domain():
    out = SourceRankerModule().run({"source_url": "https://evil-reuters.com/markets/us/example"})
    assert out.data["rank"] == "C"


def test_severity_estimator_e3_or_higher():
    out = SeverityEstimator().run(_raw_event())
    assert out.data["severity"] in ("E3", "E4")


def test_event_objectifier_id_format():
    out = EventObjectifier().run(
        {
            "headline": "test headline",
            "source_url": "https://example.com",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": "C",
            "source_rank": "B",
            "severity": "E2",
            "sequence": 1,
        }
    )
    assert out.data["event_id"].startswith("ME-C-")
    assert ".V" in out.data["event_id"]


def test_intel_pipeline_end_to_end():
    out = IntelPipeline().run(_raw_event())
    assert "event_object" in out
    assert out["event_object"]["severity"] in ("E0", "E1", "E2", "E3", "E4")
