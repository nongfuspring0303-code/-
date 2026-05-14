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
                "event_id": "evt-8",
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
    def __init__(self, data=None):
        self._data = data or {
            "lifecycle_state": "Active",
            "internal_state": "ACTIVE_TRACK",
            "catalyst_state": "Active",
            "stale_event": {"is_stale": False},
        }

    def run(self, payload):
        return _Obj(self._data)


class _FakeFatigue:
    def __init__(self, data=None):
        self._data = data or {
            "fatigue_final": 10,
            "fatigue_score": 10,
            "fatigue_bucket": "low",
            "watch_mode": False,
                "a_minus_1_discount_factor": 1.0,
        }

    def run(self, payload):
        return _Obj(self._data)


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


def assert_advisory_subsurface_boundary(surface, expected_name: str) -> None:
    assert surface["compatibility_surface"] == expected_name
    assert surface["compatibility_only"] is True
    assert surface["output_authority"] == "advisory_only"
    assert surface["production_authority"] is False
    assert surface["allows_final_selection"] is False
    assert surface["allows_execution"] is False
    assert surface["allows_broker_action"] is False
    assert surface["final_action_allowed"] is False
    assert surface["final_recommendation_allowed"] is False
    assert surface["release_status"] == "observe_only"
    assert surface["requires_downstream_adjudication"] is True
    assert surface["trace_id"]
    assert surface["event_id"]


def _runner(
    tmp_path: Path,
    *,
    enable_advisory_governance: bool = True,
    enable_cross_news_guard: bool = True,
    enable_crowding_guard: bool = True,
    enable_lifecycle_fatigue_governance: bool = True,
    lifecycle_data=None,
    fatigue_data=None,
) -> FullWorkflowRunner:
    r = FullWorkflowRunner(audit_dir=str(tmp_path))
    r.intel = _FakeIntel()
    r.lifecycle = _FakeLifecycle(lifecycle_data)
    r.fatigue = _FakeFatigue(fatigue_data)
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
        "enable_output_adapter_v5": False,
        "enable_gate_diagnostics": False,
        "enable_advisory_governance": enable_advisory_governance,
        "enable_cross_news_guard": enable_cross_news_guard,
        "enable_crowding_guard": enable_crowding_guard,
        "enable_lifecycle_fatigue_governance": enable_lifecycle_fatigue_governance,
    }
    return r


def test_advisory_governance_flag_off_omits_surface(tmp_path: Path) -> None:
    out = _runner(tmp_path, enable_advisory_governance=False).run({"headline": "QCOM jumps"})
    assert "advisory_governance" not in out["analysis"]
    assert "lifecycle_fatigue_governance" not in out["analysis"]
    assert "cross_news_governance" not in out["analysis"]
    assert "crowding_governance" not in out["analysis"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_advisory_governance_surface_is_advisory_only_and_non_authoritative(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["advisory_governance"]

    assert surface["status"] == "advisory_only"
    assert surface["compatibility_surface"] == "advisory_governance"
    assert surface["compatibility_only"] is True
    assert surface["output_authority"] == "advisory_only"
    assert surface["production_authority"] is False
    assert surface["allows_final_selection"] is False
    assert surface["allows_execution"] is False
    assert surface["allows_broker_action"] is False
    assert surface["final_action_allowed"] is False
    assert surface["final_recommendation_allowed"] is False
    assert surface["release_status"] == "observe_only"
    assert surface["requires_downstream_adjudication"] is True

    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_advisory_governance_aggregates_sub_governance(tmp_path: Path) -> None:
    lifecycle_data = {
        "lifecycle_state": "Active",
        "internal_state": "ACTIVE_TRACK",
        "catalyst_state": "Active",
        "stale_event": {"is_stale": True},
    }
    fatigue_data = {
        "fatigue_final": 90,
        "fatigue_score": 90,
        "fatigue_bucket": "high",
        "watch_mode": True,
        "a_minus_1_discount_factor": 0.5,
    }
    payload = {
        "headline": "QCOM jumps",
        "cross_news_conflicts": [
            {
                "symbol": "QCOM",
                "theme": "semiconductor",
                "status": "unresolved",
                "reason": "opposite_direction_news",
                "direction_a": "positive",
                "direction_b": "negative",
                "source_a": "source_a",
                "source_b": "source_b",
                "evidence": "same symbol opposite direction",
            }
        ],
        "crowding_signals": [
            {
                "symbol": "QCOM",
                "theme": "semiconductor",
                "crowded": True,
                "evidence": "theme_overcrowded",
                "candidate_count": 12,
                "threshold": 8,
            }
        ],
    }

    out = _runner(tmp_path, lifecycle_data=lifecycle_data, fatigue_data=fatigue_data).run(payload)
    surface = out["analysis"]["advisory_governance"]

    assert surface["overall_governance_status"] == surface["overall_status"]
    assert surface["overall_reason"]
    assert surface["governance_decisions"] == surface["governance_events"]

    domains = {item["domain"] for item in surface["governance_decisions"]}
    assert {"lifecycle_fatigue", "cross_news", "crowding"}.issubset(domains)

    for decision in surface["governance_decisions"]:
        assert decision["domain"]
        assert decision["gate_name"]
        assert decision["source_surface"]
        assert decision["trace_id"]
        assert decision["event_id"]
        assert "requires_human_review" in decision
        if decision["status"] != "pass":
            assert decision["reason"]

    assert_advisory_subsurface_boundary(
        out["analysis"]["lifecycle_fatigue_governance"],
        "lifecycle_fatigue_governance",
    )
    assert_advisory_subsurface_boundary(
        out["analysis"]["cross_news_governance"],
        "cross_news_governance",
    )
    assert_advisory_subsurface_boundary(
        out["analysis"]["crowding_governance"],
        "crowding_governance",
    )
