import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from execution_modules import ExitManager, LiquidityChecker, PositionSizer, RiskGatekeeper
from workflow_runner import WorkflowRunner


def test_liquidity_checker_red():
    mod = LiquidityChecker()
    out = mod.run({"vix": 35, "ted": 120, "correlation": 0.85, "spread_pct": 0.02})
    assert out.data["liquidity_state"] == "RED"


def test_liquidity_checker_near_danger_stays_yellow():
    mod = LiquidityChecker()
    out = mod.run({"vix": 28, "ted": 90, "correlation": 0.75, "spread_pct": 0.008})
    assert out.data["liquidity_state"] == "YELLOW"


def test_risk_gatekeeper_block_on_dead():
    mod = RiskGatekeeper()
    out = mod.run(
        {
            "event_state": "Dead",
            "fatigue_index": 20,
            "liquidity_state": "GREEN",
            "correlation": 0.5,
            "score": 80,
            "severity": "E3",
            "A1": 70,
        }
    )
    assert out.data["final_action"] == "FORCE_CLOSE"


def test_position_sizer_standard():
    mod = PositionSizer()
    out = mod.run(
        {
            "score": 72,
            "liquidity_state": "GREEN",
            "risk_gate_multiplier": 1.0,
            "account_equity": 100000,
        }
    )
    assert out.data["score_tier"] == "G2"
    assert out.data["final_notional"] == 50000.0


def test_position_sizer_daily_risk_limit_breach():
    mod = PositionSizer()
    out = mod.run(
        {
            "score": 90,
            "liquidity_state": "GREEN",
            "risk_gate_multiplier": 1.0,
            "account_equity": 100000,
            "daily_loss_pct": 0.06,
        }
    )
    assert out.data["risk_limit_breached"] is True
    assert out.data["final_notional"] == 0.0


def test_position_sizer_daily_risk_limit_breach_at_threshold():
    mod = PositionSizer()
    out = mod.run(
        {
            "score": 90,
            "liquidity_state": "GREEN",
            "risk_gate_multiplier": 1.0,
            "account_equity": 100000,
            "daily_loss_pct": 0.05,
        }
    )
    assert out.data["risk_limit_breached"] is True
    assert out.data["risk_limit_reason"].startswith("daily_loss_pct")
    assert out.data["risk_limit_reasons"] == ["daily_loss_pct 0.0500 >= max_loss_pct 0.0500"]


def test_position_sizer_reports_multiple_breach_reasons():
    mod = PositionSizer()
    out = mod.run(
        {
            "score": 90,
            "liquidity_state": "GREEN",
            "risk_gate_multiplier": 1.0,
            "account_equity": 100000,
            "daily_loss_pct": 0.06,
            "current_open_events": 5,
        }
    )
    assert out.data["risk_limit_breached"] is True
    assert len(out.data["risk_limit_reasons"]) == 2
    assert out.data["risk_limit_reason"].startswith("daily_loss_pct")


def test_exit_manager_has_levels():
    mod = ExitManager()
    out = mod.run({"entry_price": 100.0, "risk_per_share": 2.0, "direction": "long"})
    assert len(out.data["take_profit_levels"]) == 3
    assert out.data["hard_stop"] == 96.0
    assert out.data["direction"] == "long"


def test_exit_manager_rejects_invalid_direction():
    mod = ExitManager()
    out = mod.run({"entry_price": 100.0, "risk_per_share": 2.0, "direction": "sideways"})
    assert out.status.name == "FAILED"
    assert out.errors[0]["code"] == "INVALID_INPUT"


def test_workflow_runner_execute(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids.txt"),
        audit_dir=str(tmp_path / "logs"),
    )
    out = runner.run(
        {
            "A0": 30,
            "A-1": 70,
            "A1": 78,
            "A1.5": 60,
            "A0.5": 0,
            "severity": "E3",
            "fatigue_index": 45,
            "event_state": "Active",
            "correlation": 0.5,
            "vix": 18,
            "ted": 40,
            "spread_pct": 0.002,
            "account_equity": 100000,
            "entry_price": 100.0,
            "risk_per_share": 2.0,
            "direction": "long",
        }
    )
    assert out["final"]["action"] in ("EXECUTE", "WATCH", "BLOCK", "FORCE_CLOSE")
    assert "execution_ticket" in out["final"]
    assert out["trace_id"] == out["final"]["trace_id"]


def test_workflow_runner_idempotent_request(tmp_path):
    store = tmp_path / "seen_ids.txt"
    runner = WorkflowRunner(request_store_path=str(store), audit_dir=str(tmp_path / "logs"))
    payload = {
        "request_id": "REQ-001",
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
    }
    first = runner.run(payload)
    second = runner.run(payload)
    assert first["final"]["action"] in ("EXECUTE", "WATCH", "BLOCK", "FORCE_CLOSE", "PENDING_CONFIRM")
    assert second["final"]["action"] == "DUPLICATE_IGNORED"
    assert first["trace_id"] == "REQ-001"
    assert first["final"]["trace_id"] == "REQ-001"


def test_workflow_runner_idempotent_persisted_across_instances(tmp_path):
    store = tmp_path / "seen_ids.txt"
    p = {
        "request_id": "REQ-PERSIST-001",
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
    }
    r1 = WorkflowRunner(request_store_path=str(store), audit_dir=str(tmp_path / "logs"))
    _ = r1.run(p)
    r2 = WorkflowRunner(request_store_path=str(store), audit_dir=str(tmp_path / "logs"))
    out = r2.run(p)
    assert out["final"]["action"] == "DUPLICATE_IGNORED"
    assert out["trace_id"] == "REQ-PERSIST-001"


def test_workflow_runner_stable_trace_id_without_request_id(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_stable.txt"),
        audit_dir=str(tmp_path / "logs_stable"),
    )
    payload = {
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
    }
    first = runner.run(payload)
    second = runner.run(payload)
    assert first["request_id"] is None
    assert first["trace_id"] == second["trace_id"]
    assert first["trace_id"] == first["final"]["trace_id"]
    assert first["batch_id"] is None
    assert first["final"]["batch_id"] is None


def test_workflow_runner_propagates_batch_id(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_batch.txt"),
        audit_dir=str(tmp_path / "logs_batch"),
    )
    payload = {
        "request_id": "REQ-BATCH-001",
        "batch_id": "BATCH-REQ-BATCH-001",
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
    }
    out = runner.run(payload)
    assert out["trace_id"] == "REQ-BATCH-001"
    assert out["batch_id"] == "BATCH-REQ-BATCH-001"
    assert out["final"]["request_id"] == "REQ-BATCH-001"
    assert out["final"]["batch_id"] == "BATCH-REQ-BATCH-001"


def test_workflow_runner_live_mode_receipt(tmp_path):
    runner = WorkflowRunner(
        execution_mode="live",
        request_store_path=str(tmp_path / "seen_ids_live.txt"),
        audit_dir=str(tmp_path / "logs_live"),
    )
    out = runner.run(
        {
            "request_id": "REQ-LIVE-001",
            "A0": 30,
            "A-1": 70,
            "A1": 78,
            "A1.5": 60,
            "A0.5": 0,
            "severity": "E3",
            "fatigue_index": 45,
            "event_state": "Active",
            "correlation": 0.5,
            "vix": 18,
            "ted": 40,
            "spread_pct": 0.002,
            "account_equity": 100000,
            "entry_price": 100.0,
            "risk_per_share": 2.0,
            "direction": "long",
        }
    )
    assert out["execution_receipt"]["mode"] == "live"
    assert out["execution_receipt"]["status"] == "not_implemented"


def test_workflow_runner_normalizes_flip_long_direction(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_flip_long.txt"),
        audit_dir=str(tmp_path / "logs_flip_long"),
    )
    out = runner.run(
        {
            "request_id": "REQ-FLIP-LONG-001",
            "A0": 30,
            "A-1": 70,
            "A1": 78,
            "A1.5": 60,
            "A0.5": 0,
            "severity": "E3",
            "fatigue_index": 45,
            "event_state": "Active",
            "correlation": 0.5,
            "vix": 18,
            "ted": 40,
            "spread_pct": 0.002,
            "account_equity": 100000,
            "entry_price": 100.0,
            "risk_per_share": 2.0,
            "direction": "flip_long",
        }
    )
    assert out["direction"]["normalized"] == "long"
    assert out["direction"]["normalized_from_flip"] is True
    if out["final"]["action"] == "EXECUTE":
        assert out["execution_receipt"]["order"]["action"] == "OPEN_LONG"


def test_workflow_runner_normalizes_flip_short_direction(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_flip_short.txt"),
        audit_dir=str(tmp_path / "logs_flip_short"),
    )
    out = runner.run(
        {
            "request_id": "REQ-FLIP-SHORT-001",
            "A0": 30,
            "A-1": 70,
            "A1": 78,
            "A1.5": 60,
            "A0.5": 0,
            "severity": "E3",
            "fatigue_index": 45,
            "event_state": "Active",
            "correlation": 0.5,
            "vix": 18,
            "ted": 40,
            "spread_pct": 0.002,
            "account_equity": 100000,
            "entry_price": 100.0,
            "risk_per_share": 2.0,
            "direction": "flip_short",
        }
    )
    assert out["direction"]["normalized"] == "short"
    assert out["direction"]["normalized_from_flip"] is True
    if out["final"]["action"] == "EXECUTE":
        assert out["execution_receipt"]["order"]["action"] == "OPEN_SHORT"


def test_workflow_runner_consumes_ai_signal_adapter(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_ai.txt"),
        audit_dir=str(tmp_path / "logs_ai"),
    )
    out = runner.run(
        {
            "request_id": "REQ-AI-001",
            "event_id": "ME-C-20260402-001.V1.0",
            "severity": "E3",
            "fatigue_index": 30,
            "event_state": "Active",
            "correlation": 0.5,
            "vix": 18,
            "ted": 40,
            "spread_pct": 0.002,
            "account_equity": 100000,
            "entry_price": 100.0,
            "risk_per_share": 2.0,
            "direction": "long",
            "ai_intel_output": {
                "trace_id": "TRC-20260402-0001",
                "event_id": "ME-C-20260402-001.V1.0",
                "evidence_score": 82,
                "consistency_score": 76,
                "freshness_score": 88,
                "confidence": 81,
                "schema_version": "ai_intel_v1",
                "producer": "member-a",
                "generated_at": "2026-04-02T09:30:00Z",
                "model_id": "gpt-x",
                "prompt_version": "p1",
                "temperature": 0.1,
                "timeout_ms": 10000,
            },
        }
    )
    assert "ai_factors" in out
    assert out["ai_factors"]["A0"] == 82
    assert out["ai_factors"]["mapping_version"] == "factor_map_v1"


def test_risk_gatekeeper_unmatched_score_tier_does_not_trigger_g5(tmp_path):
    cfg = {
        "modules": {
            "RiskGatekeeper": {
                "params": {
                    "gates": {
                        "G1_liquidity": {"action": "BLOCK_NEW"},
                        "G2_lifecycle": {"action": "FORCE_CLOSE"},
                        "G3_fatigue": {"action": "BLOCK_NEW"},
                        "G4_correlation": {"action": "A15_ADJUST"},
                        "G6_policy": {"action": "DIRECTION_FLIP"},
                        "G7_ai_review": {"enabled": False},
                    },
                    "g1_liquidity": {
                        "spread_multiplier_threshold": 5,
                        "red_state_value": "RED",
                        "final_action_on_trigger": "BLOCK",
                        "human_confirm_required": True,
                    },
                    "g2_lifecycle": {
                        "blocked_states": ["Dead", "Archived"],
                        "final_action_on_trigger": "FORCE_CLOSE",
                        "human_confirm_required": False,
                    },
                    "g3_fatigue": {
                        "threshold": 85,
                        "final_action_on_trigger": "WATCH",
                        "human_confirm_required": False,
                    },
                    "g4_correlation": {
                        "threshold": 0.8,
                        "e4_position_multiplier": 0.5,
                        "default_position_multiplier": 0.0,
                        "warning": "Correlation collapse mode.",
                    },
                    "g6_policy": {
                        "intervention_value": "STRONG",
                        "a1_threshold": 60,
                        "direction_on_trigger": "flip",
                    },
                }
            },
            "PositionSizer": {
                "params": {
                    "tiers": {
                        "G1": {"score_range": [80, 100], "position_pct": 0.8},
                        "G2": {"score_range": [60, 80], "position_pct": 0.5},
                        "G3": {"score_range": [40, 60], "position_pct": 0.2},
                        "G4": {"score_range": [20, 40], "position_pct": 0.0},
                        "G5": {"score_range": [0, 5], "position_pct": 0.0},
                    }
                }
            },
        }
    }
    cfg_path = tmp_path / "risk_gatekeeper_gap.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    mod = RiskGatekeeper(config_path=str(cfg_path))
    out = mod.run(
        {
            "event_state": "Active",
            "fatigue_index": 20,
            "liquidity_state": "GREEN",
            "spread_multiplier": 1.0,
            "correlation": 0.5,
            "score": 10,
            "severity": "E3",
            "A1": 30,
            "policy_intervention": "NONE",
        }
    )
    assert out.data["final_action"] == "WATCH"
    assert out.data["first_triggered_gate"] is None
    assert out.data["decision_summary"]["triggered_gates"] == []
    assert out.data["decision_summary"]["matched_score_tier"] is None


def test_workflow_runner_pending_confirm_then_execute_same_request_id(tmp_path):
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_confirm.txt"),
        audit_dir=str(tmp_path / "logs_confirm"),
    )
    base_payload = {
        "request_id": "REQ-CONFIRM-001",
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
        "require_human_confirm": True,
        "human_confirmed": False,
    }
    pending = runner.run(base_payload)
    assert pending["final"]["action"] == "PENDING_CONFIRM"

    confirmed_payload = dict(base_payload)
    confirmed_payload["human_confirmed"] = True
    executed = runner.run(confirmed_payload)
    assert executed["final"]["action"] in ("EXECUTE", "WATCH", "BLOCK", "FORCE_CLOSE")
    assert executed["final"]["action"] != "DUPLICATE_IGNORED"
