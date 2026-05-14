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
                "event_id": "evt-6",
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
                "stock_candidates": [{"symbol": "QCOM"}, {"symbol": "AMD"}],
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


def _runner(tmp_path: Path, *, enable_path_lite: bool = True, enable_semantic_verdict_fix: bool = True) -> FullWorkflowRunner:
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
        "enable_semantic_verdict_fix": enable_semantic_verdict_fix,
        "enable_path_adjudicator_lite": enable_path_lite,
    }
    return r


def test_path_adjudicator_lite_surface_shadow_only_and_non_authoritative(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["path_adjudication_lite"]
    assert out["analysis"]["path_adjudicator_lite"] == surface

    assert surface["status"] == "shadow_only"
    assert surface["compatibility_surface"] == "path_adjudicator_lite"
    assert surface["output_authority"] == "shadow_only"
    assert surface["allows_final_selection"] is False
    assert surface["allows_execution"] is False
    assert surface["final_recommendation_allowed"] is False
    assert surface["production_authority"] is False
    assert surface["release_status"] == "observe_only"
    assert surface["requires_downstream_adjudication"] is True
    assert surface["override_allowed"] is False
    assert surface["shadow_override_suggested"] is True
    assert surface["override_scope"] == "shadow_only"
    assert surface["override_affects_final_selection"] is False
    assert surface["override_affects_execution"] is False
    assert surface["override_affects_final_recommended_stocks"] is False
    assert surface["final_path"] == "semantic_anchor_path"
    assert surface["decision_reason"] == "semantic_anchor_override"
    assert surface["accepted_paths"] == ["semantic_anchor_path"]
    assert "path_decision_log" in surface and len(surface["path_decision_log"]) >= 1
    assert surface["path_decision_log"][0]["decision"] == "accepted"
    assert surface["dominant_path"]["path"] == "semantic_anchor_path"
    assert surface["dominant_path"]["is_final"] is False
    assert surface["routing_authority_decision"]["status"] == "shadow_only"
    assert surface["routing_authority_decision"]["allows_final_selection"] is False
    assert surface["routing_authority_decision"]["allows_execution"] is False
    assert surface["routing_authority_decision"]["production_authority"] is False
    assert surface["non_final"] is True
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_path_adjudicator_lite_decision_log_and_path_buckets(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["path_adjudication_lite"]
    assert isinstance(surface["accepted_paths"], list)
    assert isinstance(surface["rejected_paths"], list)
    assert isinstance(surface["downgraded_paths"], list)
    assert isinstance(surface["competing_paths"], list)
    assert isinstance(surface["suppressed_paths"], list)
    assert surface["dominant_path"]["authority"] == "shadow_only"
    assert surface["dominant_path"]["is_final"] is False
    assert any(row["decision"] in {"accepted", "rejected", "downgraded"} for row in surface["path_decision_log"])


def test_path_adjudicator_lite_override_is_shadow_only(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["path_adjudication_lite"]
    assert surface["shadow_override_suggested"] in {True, False}
    assert surface["override_allowed"] is False
    assert surface["override_scope"] == "shadow_only"
    assert surface["override_affects_final_selection"] is False
    assert surface["override_affects_execution"] is False
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_path_adjudicator_lite_does_not_consume_final_recommended_stocks(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    def _forced_final_selection(**kwargs):
        return {
            "final_recommended_stocks": [],
            "shadow_only": True,
            "selection_mode": "forced_test",
            "decision_reason": "forced_test",
        }

    runner._run_conduction_final_selection = _forced_final_selection  # type: ignore[assignment]
    out = runner.run({"headline": "QCOM jumps"})
    surface = out["analysis"]["path_adjudication_lite"]
    assert surface["final_path"] == "semantic_anchor_path"
    assert surface["decision_reason"] == "semantic_anchor_override"
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == []
    assert out["execution"]["final"]["action"] == "WATCH"


def test_path_adjudicator_lite_flag_off_omits_surface(tmp_path: Path) -> None:
    out = _runner(tmp_path, enable_path_lite=False).run({"headline": "QCOM jumps"})

    assert "path_adjudication_lite" not in out["analysis"]
    assert "path_adjudicator_lite" not in out["analysis"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_path_adjudication_lite_conflict_case_can_manual_review(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runner.semantic = _FakeSemantic()
    runner.semantic.analyze = lambda h, s: {
        "event_type": "sector",
        "sentiment": "neutral",
        "confidence": 82,
        "verdict": "abstain",
        "recommended_chain": "sem_chain",
        "recommended_stocks": ["QCOM"],
        "a0_event_strength": 80,
        "expectation_gap": 60,
        "transmission_candidates": ["semiconductor"],
    }
    out = runner.run({"headline": "QCOM jumps"})
    surface = out["analysis"]["path_adjudication_lite"]
    assert surface["final_path"] == "abstain_manual_review_path"
    assert surface["decision_reason"] == "semantic_abstain_requires_manual_review"
    assert surface["routing_authority_decision"]["status"] == "shadow_only"
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD"]


def test_path_adjudication_lite_conflict_case_can_observe_only_shadow_path(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runner.semantic = _FakeSemantic()
    runner.semantic.analyze = lambda h, s: {
        "event_type": "other",
        "sentiment": "mixed",
        "confidence": 30,
        "verdict": "watch",
        "recommended_chain": "sem_chain",
        "recommended_stocks": [],
        "a0_event_strength": 80,
        "expectation_gap": 60,
        "transmission_candidates": [],
    }
    out = runner.run({"headline": "QCOM jumps"})
    surface = out["analysis"]["path_adjudication_lite"]
    assert surface["final_path"] == "observe_only_shadow_path"
    assert surface["decision_reason"] == "low_confidence_or_conflict"
    assert surface["non_final"] is True
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD"]
