import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner


def _runner(tmp_path):
    return FullWorkflowRunner(audit_dir=str(tmp_path / "logs"), state_db_path=str(tmp_path / "state.db"))


def test_stage5_a_gate_blockers_are_visible_and_cap_score(tmp_path):
    runner = _runner(tmp_path)
    scorecard = runner._build_trace_scorecard(
        trace_id="TRACE-A-S5-001",
        event_id="evt_a_s5_001",
        request_id="REQ-A-S5-001",
        batch_id="BATCH-A-S5-001",
        event_hash="EVHASH-A-S5-001",
        execution_in={
            "market_data_stale": True,
            "market_data_default_used": True,
            "market_data_fallback_used": False,
            "has_opportunity": True,
            "semantic_event_type": "macro",
            "sector_candidates": ["金融"],
            "ticker_candidates": ["SPY"],
            "theme_tags": ["liquidity"],
            "tradeable": True,
            "opportunity_count": 1,
        },
        execution_out={"final": {"action": "EXECUTE", "reason": "market_data_default_used + market_data_stale"}},
        conduction_out={
            "sector_impacts": [{"sector": "金融", "direction": "long", "score": 0.8}],
            "stock_candidates": [{"symbol": "SPY"}],
            "mapping_source": "rule_map",
            "needs_manual_review": False,
        },
        sectors=[{"name": "金融"}],
    )

    assert scorecard["a_gate_blocker_present"] is True
    assert scorecard["a_gate_blocker_count"] >= 2
    assert "MARKET_DATA_DEFAULT_USED" in scorecard["a_gate_blocker_codes"]
    assert "MARKET_DATA_STALE" in scorecard["a_gate_blocker_codes"]
    assert scorecard["a_score_cap_applied"] is True
    assert scorecard["scores"]["pre_cap_total_score"] > 54.0
    assert scorecard["scores"]["total_score"] <= 54.0
    assert scorecard["scores"]["grade"] == "D"
    assert scorecard["a_gate_signoff_ready"] is False


def test_stage5_a_gate_signoff_ready_without_blockers(tmp_path):
    runner = _runner(tmp_path)
    scorecard = runner._build_trace_scorecard(
        trace_id="TRACE-A-S5-002",
        event_id="evt_a_s5_002",
        request_id="REQ-A-S5-002",
        batch_id="BATCH-A-S5-002",
        event_hash="EVHASH-A-S5-002",
        execution_in={
            "market_data_stale": False,
            "market_data_default_used": False,
            "market_data_fallback_used": False,
            "has_opportunity": True,
            "semantic_event_type": "policy",
            "sector_candidates": ["科技"],
            "ticker_candidates": ["NVDA"],
            "theme_tags": ["ai"],
            "tradeable": True,
            "opportunity_count": 2,
        },
        execution_out={"final": {"action": "EXECUTE", "reason": "execute_clean_path"}},
        conduction_out={
            "sector_impacts": [{"sector": "科技", "direction": "long", "score": 0.9}],
            "stock_candidates": [{"symbol": "NVDA"}],
            "mapping_source": "rule_map",
            "needs_manual_review": False,
        },
        sectors=[{"name": "科技"}],
    )

    assert scorecard["a_gate_blocker_present"] is False
    assert scorecard["a_gate_blocker_count"] == 0
    assert scorecard["a_gate_blocker_codes"] == []
    assert scorecard["a_score_cap_applied"] is False
    assert scorecard["scores"]["total_score"] > 54.0
    assert scorecard["a_gate_signoff_ready"] is True
    assert scorecard["owner_dimensions"]["A_gate_safety"] >= 80.0
    assert scorecard["owner_dimensions"]["A_audit_completeness"] >= 80.0
