from __future__ import annotations

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
        return {
            "event_object": {
                "event_id": "evt-7",
                "category": "A",
                "severity": "E3",
                "source_rank": "A",
                "headline": payload.get("headline", "QCOM jumps"),
                "detected_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "source_rank": {"rank": "A", "needs_escalation": False},
            "severity": {"A0": 78},
        }


class _FakeLifecycle:
    def run(self, payload):
        return _Obj(
            {
                "lifecycle_state": "Active",
                "internal_state": "ACTIVE_TRACK",
                "catalyst_state": "Active",
                "time_scale": "intraday",
                "decay_profile": "medium",
                "stale_event": {"is_stale": False},
            }
        )


class _FakeFatigue:
    def run(self, payload):
        return _Obj(
            {
                "fatigue_final": 10,
                "fatigue_score": 10,
                "fatigue_bucket": "low",
                "watch_mode": False,
                "a_minus_1_discount_factor": 1.0,
            }
        )


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
    def run(self, payload):
        return _Obj(
            {
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
        )


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
        return _Obj({"primary_path": {"path_text": "main"}, "secondary_paths": [], "rejected_paths": [], "target_sector": ["Technology"], "target_leader": ["QCOM"], "target_etf": [], "target_followers": []})


class _FakeSignal:
    def run(self, payload):
        return _Obj({"score": 78, "score_decision": "WATCH", "relative_direction_score": 0.7, "absolute_direction": "positive", "driver_confidence": 0.8, "gap_score": 0.5, "execution_confidence": 0.6})


class _FakeOpportunity:
    def build_opportunity_update(self, payload):
        return {"opportunities": []}


class _FakeExecSug:
    def run(self, payload):
        return _Obj({"trade_type": "avoid", "position_sizing": {"mode": "flat", "note": "advisory_only_human_review"}})


class _FakePathQuality:
    def run(self, payload):
        return _Obj({"score": 0.5})


class _FakeExecution:
    def run(self, payload):
        return {"final": {"action": "WATCH", "reason": "missing_opportunity"}}


class _FakeStateStore:
    def get_state(self, event_id):
        return None

    def upsert_state(self, event_id, state):
        return None


def _runner(tmp_path: Path, *, enable_output_adapter: bool = True) -> FullWorkflowRunner:
    r = FullWorkflowRunner(audit_dir=str(tmp_path))
    r.intel = _FakeIntel()
    r.lifecycle = _FakeLifecycle()
    r.fatigue = _FakeFatigue()
    r.conduction = _FakeConduction()
    r.validation = _FakeValidation()
    r.semantic = _FakeSemantic()
    r.path_adjudicator = _FakePathAdj()
    r.scorer = _FakeSignal()
    r.opportunity = _FakeOpportunity()
    r.execution_suggestion_builder = _FakeExecSug()
    r.path_quality_evaluator = _FakePathQuality()
    r.execution = _FakeExecution()
    r.state_store = _FakeStateStore()
    r._load_feature_flags = lambda: {
        "enable_v5_shadow_output": True,
        "enable_replace_legacy_output": False,
        "enable_conduction_split": True,
        "enable_semantic_prepass": True,
        "enable_semantic_full_peer_expansion": False,
        "enable_market_validation_gate": False,
        "enable_semantic_verdict_fix": False,
        "enable_path_adjudicator_lite": False,
        "enable_output_adapter_v5": enable_output_adapter,
    }
    return r


def test_output_adapter_surface_shadow_only_and_immutable(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM jumps"})
    analysis = out["analysis"]
    surface = analysis["output_adapter"]

    assert analysis["output_adapter_v5"] == surface
    assert surface["status"] == "shadow_only"
    assert surface["compatibility_surface"] == "output_adapter"
    assert surface["compatibility_only"] is True
    assert surface["source_surface"] == "conduction_final_selection.final_recommended_stocks"
    assert surface["adapter_mode"] == "compatibility_passthrough"
    assert surface["mutation_detected"] is False
    assert surface["mutation_rate"] == 0.0
    assert surface["output_adapter_mutation_rate"] == 0.0
    assert surface["output_authority"] == "shadow_only"
    assert surface["allows_final_selection"] is False
    assert surface["allows_execution"] is False
    assert surface["allows_broker_action"] is False
    assert surface["final_action_allowed"] is False
    assert surface["production_authority"] is False
    assert surface["release_status"] == "observe_only"
    assert surface["requires_downstream_adjudication"] is True
    assert surface["legacy_final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert surface["adapted_output"]["recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_output_adapter_flag_off_omits_surface(tmp_path: Path) -> None:
    out = _runner(tmp_path, enable_output_adapter=False).run({"headline": "QCOM jumps"})
    assert "output_adapter" not in out["analysis"]
    assert "output_adapter_v5" not in out["analysis"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]


def test_output_adapter_mutation_metrics_detect_reorder_and_fail_closed() -> None:
    metrics = FullWorkflowRunner._compute_output_adapter_mutation(
        legacy_symbols=["QCOM", "AMD", "NVDA"],
        adapted_symbols=["AMD", "QCOM", "NVDA"],
    )
    assert metrics["mutation_detected"] is True
    assert metrics["mutation_rate"] > 0.0


def test_output_adapter_fail_closed_when_mutation_detected(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    def _forced_metrics(legacy_symbols, adapted_symbols):
        return {
            "legacy_symbols": list(legacy_symbols),
            "adapted_symbols": list(adapted_symbols),
            "same_sequence": False,
            "same_set": False,
            "mismatch_count": 1,
            "mutation_rate": 0.5,
            "mutation_detected": True,
        }

    runner._compute_output_adapter_mutation = _forced_metrics  # type: ignore[assignment]
    out = runner.run({"headline": "QCOM jumps"})
    surface = out["analysis"]["output_adapter"]
    assert surface["adapter_mode"] == "downgraded_fail_closed"
    assert surface["downgrade_reason"] == "adapter_mutation_detected"
    assert surface["mutation_detected"] is True
    assert surface["output_adapter_mutation_rate"] > 0.0
