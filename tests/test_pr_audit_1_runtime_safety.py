from __future__ import annotations

import json
from pathlib import Path

from edt_module_base import ModuleStatus
from full_workflow_runner import FullWorkflowRunner


class _Obj:
    def __init__(self, data):
        self.data = data
        self.status = ModuleStatus.SUCCESS
        self.errors = []


class _FakeIntel:
    def run(self, payload):
        event_object = {
            "event_id": "evt-audit-1",
            "category": "A",
            "severity": "E3",
            "source_rank": "BROKEN_SHOULD_NOT_BE_USED",
            "headline": payload.get("headline", "QCOM jumps"),
            "detected_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        if payload.get("drop_event_category"):
            event_object["category"] = None
        out = {
            "event_object": event_object,
            "severity": {"A0": 78},
        }
        if not payload.get("drop_source_rank"):
            out["source_rank"] = {"rank": "A", "needs_escalation": False, "confidence": 0.9}
        return out


class _FakeLifecycle:
    def __init__(self):
        self.last_payload = None
        self.drop_keys = False

    def run(self, payload):
        self.last_payload = dict(payload)
        data = {
            "lifecycle_state": "Active",
            "internal_state": "ACTIVE_TRACK",
            "catalyst_state": "Active",
            "stale_event": {"is_stale": False},
        }
        if self.drop_keys:
            data.pop("lifecycle_state", None)
            data.pop("internal_state", None)
            data.pop("catalyst_state", None)
        return _Obj(data)


class _FakeFatigue:
    def __init__(self):
        self.drop_fatigue_score = False
        self.drop_fatigue_final = False

    def run(self, payload):
        data = {
            "fatigue_final": 10,
            "fatigue_score": 10,
            "fatigue_bucket": "low",
            "watch_mode": False,
            "a_minus_1_discount_factor": 1.0,
        }
        if self.drop_fatigue_score:
            data.pop("fatigue_score", None)
        if self.drop_fatigue_final:
            data.pop("fatigue_final", None)
        return _Obj(data)


class _FakeConduction:
    def run(self, payload):
        return _Obj(
            {
                "confidence": 76,
                "conduction_path": ["a", "b", "c"],
                "sector_impacts": [{"sector": "Technology", "direction": "benefit", "impact_score": 0.6, "confidence": 0.8}],
                "stock_candidates": [{"symbol": "QCOM"}, {"symbol": "AMD"}, {"symbol": "NVDA"}],
                "mapping_source": "rule",
                "needs_manual_review": False,
            }
        )


class _FakeValidation:
    def __init__(self, missing_a1: bool = False):
        self.missing_a1 = missing_a1

    def run(self, payload):
        data = {
            "A1": 74,
            "checks": [],
            "a1_market_validation": "pass",
            "market_data_source": "payload_direct",
            "market_data_present": True,
            "market_data_stale": False,
            "market_data_default_used": False,
            "market_data_fallback_used": False,
            "sector_confirmation": "strong",
            "leader_confirmation": "confirmed",
            "macro_confirmation": "supportive",
        }
        if self.missing_a1:
            data.pop("A1", None)
        return _Obj(data)


class _FakeSemantic:
    def analyze(self, headline, summary):
        return {
            "event_type": "sector",
            "sentiment": "positive",
            "confidence": 82,
            "verdict": "long",
            "recommended_chain": "sem_chain",
            "recommended_stocks": ["QCOM"],
            "a0_event_strength": 80,
            "expectation_gap": 60,
            "transmission_candidates": ["semiconductor"],
        }

    def analyze_event(self, headline, summary, semantic_output, event_id, event_time):
        return {"event_type": semantic_output.get("event_type", "unknown"), "event_time": event_time, "evidence_grade": "B"}


class _FakePathAdj:
    def run(self, payload):
        return _Obj(
            {
                "primary_path": {"path_text": "main"},
                "secondary_paths": [],
                "rejected_paths": [],
                "target_sector": ["Technology"],
                "target_leader": ["QCOM"],
                "target_etf": [],
                "target_followers": [],
            }
        )


class _FakeSignal:
    def run(self, payload):
        return _Obj(
            {
                "score": 78,
                "score_decision": "WATCH",
                "relative_direction_score": 0.7,
                "absolute_direction": "positive",
                "driver_confidence": 0.8,
                "gap_score": 0.5,
                "execution_confidence": 0.6,
            }
        )


class _FakeOpportunity:
    def __init__(self):
        self.force_has_opportunity = False

    def build_opportunity_update(self, payload):
        if self.force_has_opportunity:
            return {
                "opportunities": [
                    {
                        "symbol": "QCOM",
                        "decision_price": 100.0,
                        "decision_price_source": "mock",
                        "needs_price_refresh": False,
                        "final_action": "WATCH",
                    }
                ]
            }
        return {"opportunities": []}


class _CapturingExecutionSuggestion:
    def __init__(self):
        self.last_payload = None

    def run(self, payload):
        self.last_payload = dict(payload)
        return _Obj({"trade_type": "avoid", "position_sizing": {"mode": "flat"}})


class _FakePathQuality:
    def run(self, payload):
        return _Obj({"score": 0.5})


class _MutatingExecution:
    def __init__(self):
        self.last_payload = None
        self.called = False

    def run(self, payload):
        self.called = True
        self.last_payload = dict(payload)
        sector_impacts = payload.get("sector_impacts")
        if isinstance(sector_impacts, list):
            sector_impacts.append({"sector": "MUTATED", "direction": "watch"})
        return {"final": {"action": "WATCH", "reason": "missing_opportunity"}}


class _FakeStateStore:
    def __init__(self):
        self.last_event_id = None
        self.last_state = None

    def get_state(self, event_id):
        return None

    def upsert_state(self, event_id, state):
        self.last_event_id = event_id
        self.last_state = dict(state)
        return None


def _runner(
    tmp_path: Path, *, missing_a1: bool = False
) -> tuple[FullWorkflowRunner, _FakeLifecycle, _FakeFatigue, _CapturingExecutionSuggestion, _MutatingExecution, _FakeStateStore, _FakeOpportunity]:
    lifecycle = _FakeLifecycle()
    fatigue = _FakeFatigue()
    execution_suggestion = _CapturingExecutionSuggestion()
    execution = _MutatingExecution()
    state_store = _FakeStateStore()

    r = FullWorkflowRunner(audit_dir=str(tmp_path))
    r.intel = _FakeIntel()
    r.lifecycle = lifecycle
    r.fatigue = fatigue
    r.conduction = _FakeConduction()
    r.validation = _FakeValidation(missing_a1=missing_a1)
    r.semantic = _FakeSemantic()
    r.path_adjudicator = _FakePathAdj()
    r.scorer = _FakeSignal()
    opportunity = _FakeOpportunity()
    r.opportunity = opportunity
    r.execution_suggestion_builder = execution_suggestion
    r.path_quality_evaluator = _FakePathQuality()
    r.execution = execution
    r.state_store = state_store
    return r, lifecycle, fatigue, execution_suggestion, execution, state_store, opportunity


def test_symbols_requested_none_uses_derived_symbols(tmp_path: Path) -> None:
    runner, _, _, _, _, _, _ = _runner(tmp_path)
    runner.run(
        {
            "headline": "QCOM jumps",
            "symbols_requested": None,
            "symbols_returned": None,
            "price_changes": {"qcom": 0.05, "amd": 0.03, "nvda": 0.04},
            "volume_changes": {"qcom": 0.10, "amd": 0.07, "nvda": 0.08},
        }
    )
    rec = json.loads(Path(runner.market_data_provenance_log_path).read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["symbols_requested"] == ["AMD", "NVDA", "QCOM"]
    assert rec["symbols_returned"] == ["AMD", "NVDA", "QCOM"]


def test_symbols_requested_list_with_none_does_not_emit_NONE(tmp_path: Path) -> None:
    runner, _, _, _, _, _, _ = _runner(tmp_path)
    runner.run(
        {
            "headline": "QCOM jumps",
            "symbols_requested": [None, "AAPL"],
            "symbols_returned": [None, "AAPL"],
        }
    )
    rec = json.loads(Path(runner.market_data_provenance_log_path).read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["symbols_requested"] == ["AAPL"]
    assert rec["symbols_returned"] == ["AAPL"]
    assert "NONE" not in rec["symbols_requested"]
    assert "NONE" not in rec["symbols_returned"]


def test_symbols_requested_empty_list_is_preserved(tmp_path: Path) -> None:
    runner, _, _, _, _, _, _ = _runner(tmp_path)
    runner.run({"headline": "QCOM jumps", "symbols_requested": [], "symbols_returned": []})
    rec = json.loads(Path(runner.market_data_provenance_log_path).read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["symbols_requested"] == []
    assert rec["symbols_returned"] == []


def test_symbols_requested_explicit_list_is_preserved(tmp_path: Path) -> None:
    runner, _, _, _, _, _, _ = _runner(tmp_path)
    runner.run({"headline": "QCOM jumps", "symbols_requested": ["AAPL"], "symbols_returned": ["AAPL"]})
    rec = json.loads(Path(runner.market_data_provenance_log_path).read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["symbols_requested"] == ["AAPL"]
    assert rec["symbols_returned"] == ["AAPL"]


def test_symbols_requested_missing_key_uses_derived_symbols(tmp_path: Path) -> None:
    runner, _, _, _, _, _, _ = _runner(tmp_path)
    runner.run({"headline": "QCOM jumps", "price_changes": {"qcom": 0.05, "amd": 0.03, "nvda": 0.04}})
    rec = json.loads(Path(runner.market_data_provenance_log_path).read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["symbols_requested"] == ["AMD", "NVDA", "QCOM"]


def test_conduction_out_does_not_alias_candidate_generation_output(tmp_path: Path) -> None:
    runner, _, _, _, _, _, _ = _runner(tmp_path)
    out = runner.run({"headline": "QCOM jumps"})
    cand_sectors = [x.get("sector") for x in out["analysis"]["conduction_candidate_generation"]["sector_impacts"]]
    assert "MUTATED" not in cand_sectors


def test_fatigue_score_falls_back_to_fatigue_final_for_execution_suggestion(tmp_path: Path) -> None:
    runner, _, fatigue, execution_suggestion, _, _, _ = _runner(tmp_path)
    fatigue.drop_fatigue_score = True
    out = runner.run({"headline": "QCOM jumps"})
    assert execution_suggestion.last_payload is None
    analysis = out["analysis"]
    assert analysis.get("execution_suggestion_status") == "failed"
    errors = analysis.get("execution_suggestion_errors") or []
    assert errors and errors[0].get("code") == "MISSING_FATIGUE_SCORE"
    runtime_safety = analysis.get("runtime_safety_contract") or {}
    assert runtime_safety.get("status") == "degraded"
    assert "missing_fatigue_score" in (runtime_safety.get("issues") or [])


def test_fatigue_score_missing_both_keys_uses_safe_default(tmp_path: Path) -> None:
    runner, _, fatigue, execution_suggestion, _, _, _ = _runner(tmp_path)
    fatigue.drop_fatigue_score = True
    fatigue.drop_fatigue_final = True
    out = runner.run({"headline": "QCOM jumps"})
    assert execution_suggestion.last_payload is None
    analysis = out["analysis"]
    assert analysis.get("execution_suggestion_status") == "failed"
    errors = analysis.get("execution_suggestion_errors") or []
    assert errors and errors[0].get("code") == "MISSING_FATIGUE_SCORE"
    runtime_safety = analysis.get("runtime_safety_contract") or {}
    assert runtime_safety.get("status") == "degraded"
    assert "missing_fatigue_score_and_fatigue_final" in (runtime_safety.get("issues") or [])


def test_source_rank_for_lifecycle_and_execution_uses_intel_source_rank_object(tmp_path: Path) -> None:
    runner, lifecycle, _, _, execution, _, _ = _runner(tmp_path)
    runner.run({"headline": "QCOM jumps"})
    assert lifecycle.last_payload is not None
    assert lifecycle.last_payload["source_rank"] == "A"
    assert execution.last_payload is not None
    assert execution.last_payload["source_rank"]["rank"] == "A"
    assert execution.last_payload["source_rank"] != "BROKEN_SHOULD_NOT_BE_USED"


def test_missing_validation_a1_does_not_crash_signal_or_execution_payload(tmp_path: Path) -> None:
    runner, _, _, _, execution, _, _ = _runner(tmp_path, missing_a1=True)
    out = runner.run({"headline": "QCOM jumps"})
    analysis = out["analysis"]
    assert analysis.get("signal_status") == "failed"
    signal_errors = analysis.get("signal_errors") or []
    assert signal_errors and signal_errors[0].get("code") == "MISSING_VALIDATION_A1"
    assert analysis.get("execution_suggestion_status") == "failed"
    exec_errors = analysis.get("execution_suggestion_errors") or []
    assert exec_errors and exec_errors[0].get("code") == "MISSING_VALIDATION_A1"
    assert execution.called is False
    assert execution.last_payload is None
    assert out["execution"]["final"]["action"] == "BLOCK"
    assert out["execution"]["final"]["reason"] == "runtime_safety_fail_closed"
    runtime_safety = analysis.get("runtime_safety_contract") or {}
    assert runtime_safety.get("status") == "degraded"
    assert "missing_validation_a1" in (runtime_safety.get("issues") or [])
    assert runtime_safety.get("execution_authority_blocked") is True


def test_run_does_not_crash_on_missing_lifecycle_keys(tmp_path: Path) -> None:
    runner, lifecycle, _, _, execution, state_store, _ = _runner(tmp_path)
    lifecycle.drop_keys = True
    out = runner.run({"headline": "QCOM jumps", "drop_event_category": True})
    assert out["execution"]["final"]["action"] == "WATCH"
    assert execution.last_payload is not None
    assert state_store.last_state is not None
    assert state_store.last_state["internal_state"] is not None
    assert state_store.last_state["lifecycle_state"] is not None
    assert state_store.last_state["catalyst_state"] is not None
    assert state_store.last_state["metadata"]["category"] is not None


def test_missing_source_rank_does_not_raise_key_error(tmp_path: Path) -> None:
    runner, lifecycle, _, _, execution, _, _ = _runner(tmp_path)
    out = runner.run({"headline": "QCOM jumps", "drop_source_rank": True})
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert lifecycle.last_payload is not None
    assert lifecycle.last_payload["source_rank"] == "unknown"
    assert execution.last_payload is not None
    source_rank = execution.last_payload.get("source_rank")
    assert isinstance(source_rank, dict)
    assert source_rank.get("rank") == "unknown"


def test_missing_a1_with_has_opportunity_blocks_execution_authority(tmp_path: Path) -> None:
    runner, _, _, _, execution, _, opportunity = _runner(tmp_path, missing_a1=True)
    opportunity.force_has_opportunity = True
    out = runner.run({"headline": "QCOM jumps"})
    assert out["execution"]["final"]["action"] == "BLOCK"
    assert execution.called is False
    runtime_safety = out["analysis"].get("runtime_safety_contract") or {}
    assert runtime_safety.get("execution_authority_blocked") is True


def test_missing_fatigue_score_with_has_opportunity_blocks_execution_authority(tmp_path: Path) -> None:
    runner, _, fatigue, _, execution, _, opportunity = _runner(tmp_path)
    fatigue.drop_fatigue_score = True
    opportunity.force_has_opportunity = True
    out = runner.run({"headline": "QCOM jumps"})
    assert out["analysis"].get("execution_suggestion_status") == "failed"
    assert out["execution"]["final"]["action"] == "BLOCK"
    assert execution.called is False
    runtime_safety = out["analysis"].get("runtime_safety_contract") or {}
    assert runtime_safety.get("execution_authority_blocked") is True
