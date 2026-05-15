import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from shadow_comparator import compare_and_gate, compare_shadow, evaluate_shadow_gate


def test_compare_shadow_reports_match_rates_and_p95_delta():
    a = [
        {
            "trace_id": f"t{i}",
            "action": "TRADE" if i % 2 == 0 else "WATCH",
            "dominant_path": {"name": f"p{i % 3}"},
            "sector_rankings": {"primary_sector": ["technology", "energy", "utilities"][i % 3]},
            "score_100": 80 + i,
        }
        for i in range(20)
    ]
    b = [
        {
            "trace_id": f"t{i}",
            "action": "TRADE" if i % 2 == 0 else "WATCH",
            "dominant_path": {"name": f"p{i % 3}"},
            "sector_rankings": {"primary_sector": ["technology", "energy", "utilities"][i % 3]},
            "score_100": 78 + i,
        }
        for i in range(20)
    ]
    out = compare_shadow(a, b)
    assert out["samples"] == 20
    assert out["action_match_rate"] == 1.0
    assert out["path_match_rate"] == 1.0
    assert out["sector_match_rate"] == 1.0
    assert out["score_delta_p95"] == 2.0


def test_shadow_gate_passes_when_metrics_meet_thresholds():
    metrics = {
        "samples": 50,
        "action_match_rate": 0.96,
        "path_match_rate": 0.91,
        "sector_match_rate": 0.92,
        "score_delta_p95": 7.0,
    }
    gate_policy = {
        "shadow": {
            "min_events_per_day": 30,
            "action_match_rate_min": 0.95,
            "path_match_rate_min": 0.90,
            "sector_match_rate_min": 0.90,
            "score_delta_p95_max": 8.0,
        }
    }
    out = evaluate_shadow_gate(metrics, gate_policy)
    assert out["passed"] is True
    assert out["failed_checks"] == []
    assert out["gate_reason_code"] == "ALL_PASSED"
    assert out["gate_reason_codes"] == []


def test_shadow_gate_fails_when_any_metric_below_threshold():
    metrics = {
        "samples": 10,
        "action_match_rate": 0.80,
        "path_match_rate": 0.70,
        "sector_match_rate": 0.95,
        "score_delta_p95": 9.0,
    }
    gate_policy = {
        "shadow": {
            "min_events_per_day": 30,
            "action_match_rate_min": 0.95,
            "path_match_rate_min": 0.90,
            "sector_match_rate_min": 0.90,
            "score_delta_p95_max": 8.0,
        }
    }
    out = evaluate_shadow_gate(metrics, gate_policy)
    assert out["passed"] is False
    assert "samples" in out["failed_checks"]
    assert "action_match_rate" in out["failed_checks"]
    assert "path_match_rate" in out["failed_checks"]
    assert "score_delta_p95" in out["failed_checks"]
    assert out["gate_reason_code"] in {
        "SHADOW_SAMPLE_INSUFFICIENT",
        "SHADOW_ACTION_MISMATCH",
        "SHADOW_PATH_MISMATCH",
        "SHADOW_SCORE_DELTA_EXCEEDED",
    }
    assert out["gate_reason_codes"]


def test_compare_and_gate_combines_metrics_and_gate_result():
    a = [{"trace_id": "t1", "action": "TRADE", "dominant_path": {"name": "p1"}, "sector_rankings": {"primary_sector": "tech"}, "score_100": 80}]
    b = [{"trace_id": "t1", "action": "TRADE", "dominant_path": {"name": "p1"}, "sector_rankings": {"primary_sector": "tech"}, "score_100": 79}]
    gate_policy = {
        "shadow": {
            "min_events_per_day": 1,
            "action_match_rate_min": 0.95,
            "path_match_rate_min": 0.90,
            "sector_match_rate_min": 0.90,
            "score_delta_p95_max": 8.0,
        }
    }
    out = compare_and_gate(a, b, gate_policy)
    assert "metrics" in out
    assert "gate" in out
    assert out["metrics"]["samples"] == 1
    assert out["gate"]["passed"] is True
