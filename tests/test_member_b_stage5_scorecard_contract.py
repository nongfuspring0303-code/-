import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from full_workflow_runner import FullWorkflowRunner


REQUIRED_FIELDS = [
    "trace_id",
    "event_hash",
    "semantic_event_type",
    "sector_candidates",
    "ticker_candidates",
    "theme_tags",
    "tradeable",
    "opportunity_count",
    "final_action",
    "final_reason",
    "sectors[]",
    "sector_impacts",
    "stock_candidates",
    "mapping_source",
    "needs_manual_review",
    "placeholder_count",
    "non_whitelist_sector_count",
    "ticker_truth_source_hit",
    "ticker_truth_source_miss",
    "sector_quality_score",
    "ticker_quality_score",
    "output_quality_score",
    "mapping_acceptance_score",
    "b_overall_score",
    "b_signoff_ready",
    "decision_price",
    "decision_price_source",
    "needs_price_refresh",
]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _stage5_payload() -> dict:
    return {
        "request_id": "REQ-S5-B-CONTRACT-001",
        "batch_id": "BATCH-S5-B-CONTRACT-001",
        "headline": "Fed announces emergency liquidity action after tariff shock",
        "source": "https://www.reuters.com/markets/us/example",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 24,
        "vix_change_pct": 20,
        "spx_move_pct": 1.8,
        "sector_move_pct": 3.0,
        "sequence": 1,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
        "theme_tags": ["macro_event", "liquidity_support"],
    }


def _build_contract_row(execution_in_override: Optional[dict] = None, execution_out_override: Optional[dict] = None) -> dict:
    runner = FullWorkflowRunner()
    execution_in = {
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "has_opportunity": True,
        "semantic_event_type": "macro_policy",
        "sector_candidates": ["Technology"],
        "ticker_candidates": ["AAPL"],
        "sectors": ["Technology"],
        "sector_impacts": [{"sector": "Technology", "direction": "benefit"}],
        "stock_candidates": [{"symbol": "AAPL", "sector": "Technology"}],
        "mapping_source": "template:rate_cut_chain",
        "needs_manual_review": False,
        "theme_tags": ["macro_event"],
        "tradeable": True,
        "opportunity_count": 1,
    }
    if execution_in_override:
        execution_in.update(execution_in_override)

    execution_out = {"final": {"action": "EXECUTE", "reason": "passed_gate_and_executed"}}
    if execution_out_override:
        execution_out = execution_out_override

    return runner._build_trace_scorecard(
        trace_id="TRACE-B-S5-001",
        event_id="ME-S5-B-001",
        request_id="REQ-S5-B-001",
        batch_id="BATCH-S5-B-001",
        event_hash="EVH-S5-B-001",
        execution_in=execution_in,
        execution_out=execution_out,
    )


def test_stage5_b_required_fields_present(tmp_path):
    runner = FullWorkflowRunner(audit_dir=str(tmp_path / "logs"), state_db_path=str(tmp_path / "state.db"))
    runner.run(_stage5_payload())

    score_rows = _read_jsonl(tmp_path / "logs" / "trace_scorecard.jsonl")
    assert score_rows, "trace_scorecard.jsonl should not be empty"
    latest = score_rows[-1]

    for field in REQUIRED_FIELDS:
        assert field in latest, f"missing required field: {field}"

    assert isinstance(latest["sector_candidates"], list)
    assert isinstance(latest["ticker_candidates"], list)
    assert isinstance(latest["sector_impacts"], list)
    assert isinstance(latest["stock_candidates"], list)
    assert isinstance(latest["b_signoff_ready"], bool)


def test_stage5_b_non_whitelist_sector_score_fails():
    row = _build_contract_row(
        execution_in_override={
            "sectors": ["NON_WHITELIST_SECTOR_X"],
            "sector_candidates": ["NON_WHITELIST_SECTOR_X"],
            "sector_impacts": [{"sector": "NON_WHITELIST_SECTOR_X", "direction": "benefit"}],
        }
    )
    assert row["non_whitelist_sector_count"] > 0
    assert row["sector_quality_score"] < 80
    assert row["b_signoff_ready"] is False


def test_stage5_b_ticker_truth_source_miss_fails():
    row = _build_contract_row(
        execution_in_override={
            "ticker_candidates": ["ZZZZ"],
            "stock_candidates": [{"symbol": "ZZZZ", "sector": "Technology"}],
        }
    )
    assert row["ticker_truth_source_miss"] > 0
    assert row["ticker_quality_score"] < 80
    assert row["b_signoff_ready"] is False


def test_stage5_b_placeholder_leakage_threshold_enforced():
    row = _build_contract_row(
        execution_in_override={
            "theme_tags": ["placeholder_token"],
        }
    )
    assert row["placeholder_count"] > 0
    assert row["output_quality_score"] < 80
    assert row["b_signoff_ready"] is False


def test_stage5_b_signoff_ready_requires_all_quality_conditions():
    good = _build_contract_row()
    assert good["sector_quality_score"] >= 80
    assert good["ticker_quality_score"] >= 80
    assert good["output_quality_score"] >= 80
    assert good["mapping_acceptance_score"] >= 80
    assert good["b_signoff_ready"] is True

    bad = _build_contract_row(
        execution_in_override={
            "ticker_candidates": ["ZZZZ"],
            "stock_candidates": [{"symbol": "ZZZZ", "sector": "Technology"}],
        }
    )
    assert bad["ticker_quality_score"] < 80
    assert bad["b_signoff_ready"] is False


def test_stage5_b_decision_price_written_when_provided():
    """S6-R014: decision_price passes through execution_in -> trace_scorecard.
    Test ID: S6-T014-01"""
    row = _build_contract_row(
        execution_in_override={
            "decision_price": 271.35,
            "decision_price_source": "live",
            "needs_price_refresh": False,
        }
    )
    assert row["decision_price"] == 271.35
    assert row["decision_price_source"] == "live"
    assert row["needs_price_refresh"] is False


def test_stage5_b_decision_price_null_when_missing():
    """S6-R014: decision_price defaults to None when missing,
    decision_price_source normalizes to 'missing'.
    Test ID: S6-T014-02"""
    row = _build_contract_row()
    assert row["decision_price"] is None
    assert row["decision_price_source"] == "missing"
    assert row["needs_price_refresh"] is None


def test_stage5_b_decision_price_source_missing():
    """S6-R014: decision_price_source='missing' preserved through chain.
    Test ID: S6-T014-03"""
    row = _build_contract_row(
        execution_in_override={
            "decision_price": None,
            "decision_price_source": "missing",
            "needs_price_refresh": True,
        }
    )
    assert row["decision_price"] is None
    assert row["decision_price_source"] == "missing"
    assert row["needs_price_refresh"] is True


def test_stage5_b_decision_prices_by_symbol_propagated():
    """S6-R014: decision_prices_by_symbol dict propagates to trace_scorecard.
    Test ID: S6-T014-04"""
    by_symbol = {
        "AAPL": {
            "decision_price": 271.35,
            "decision_price_source": "live",
            "needs_price_refresh": False,
            "final_action": "EXECUTE",
        }
    }
    row = _build_contract_row(
        execution_in_override={
            "decision_prices_by_symbol": by_symbol,
        }
    )
    assert "decision_prices_by_symbol" in row
    assert row["decision_prices_by_symbol"] == by_symbol
    assert row["decision_prices_by_symbol"]["AAPL"]["decision_price"] == 271.35
