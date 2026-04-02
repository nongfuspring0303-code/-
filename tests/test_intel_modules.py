import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

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

