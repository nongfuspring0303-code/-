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
                "event_id": "evt-5",
                "category": "A",
                "severity": "E3",
                "source_rank": "A",
                "headline": payload.get("headline", "QCOM peers up"),
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
        return _Obj({"fatigue_final": 10, "fatigue_score": 10, "fatigue_bucket": "low", "watch_mode": False, "a_minus_1_discount_factor": 1.0})


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
    def __init__(
        self,
        *,
        market_data_present: bool = True,
        market_data_stale: bool = False,
        market_data_default_used: bool = False,
        market_data_fallback_used: bool = False,
    ) -> None:
        self.market_data_present = market_data_present
        self.market_data_stale = market_data_stale
        self.market_data_default_used = market_data_default_used
        self.market_data_fallback_used = market_data_fallback_used

    def run(self, payload):
        return _Obj(
            {
                "A1": 74,
                "checks": [],
                "a1_market_validation": "pass" if self.market_data_present else "fail",
                "market_data_source": "payload_direct" if self.market_data_present else "missing",
                "market_data_present": self.market_data_present,
                "market_data_stale": self.market_data_stale,
                "market_data_default_used": self.market_data_default_used,
                "market_data_fallback_used": self.market_data_fallback_used,
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
            "confidence": 88,
            "recommended_chain": "sem_chain",
            "recommended_stocks": ["QCOM", "AMD", "AVGO"],
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


def _runner(
    tmp_path: Path,
    *,
    market_validation_gate: bool = True,
    market_data_present: bool = True,
    market_data_stale: bool = False,
    market_data_default_used: bool = False,
    market_data_fallback_used: bool = False,
) -> FullWorkflowRunner:
    r = FullWorkflowRunner(audit_dir=str(tmp_path))
    r.intel = _FakeIntel()
    r.lifecycle = _FakeLifecycle()
    r.fatigue = _FakeFatigue()
    r.conduction = _FakeConduction()
    r.validation = _FakeValidation(
        market_data_present=market_data_present,
        market_data_stale=market_data_stale,
        market_data_default_used=market_data_default_used,
        market_data_fallback_used=market_data_fallback_used,
    )
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
        "enable_semantic_full_peer_expansion": True,
        "enable_market_validation_gate": market_validation_gate,
    }
    return r


def test_peer_market_validation_shadow_surface_filters_fully_reacted_and_lagging(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM peers up 5%"})
    analysis = out["analysis"]

    assert "peer_market_validation" in analysis
    surface = analysis["peer_market_validation"]
    assert surface["status"] == "shadow_only"
    assert surface["compatibility_surface"] == "peer_market_validation"
    assert surface["compatibility_only"] is True
    assert surface["source_surface"] == "semantic_full_peer_expansion"
    assert surface["validation_mode"] == "peer_scoped_market_validation"
    assert surface["validated_count"] > 0
    assert surface["rejected_count"] > 0
    assert any(item["validation_reason"] == "lagging_peer" for item in surface["validated_peer_candidates"])
    assert any(item["validation_reason"] == "fully_reacted" for item in surface["rejected_peer_candidates"])
    assert all(item["is_final"] is False for item in surface["validated_peer_candidates"] + surface["rejected_peer_candidates"])
    assert all(item["status"] == "validated" for item in surface["validated_peer_candidates"])
    assert all(item["status"] == "rejected" for item in surface["rejected_peer_candidates"])
    assert analysis["semantic_full_peer_expansion"]["peer_candidates"]
    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_peer_market_validation_missing_market_data_does_not_default_validate(tmp_path: Path) -> None:
    out = _runner(
        tmp_path,
        market_data_present=False,
        market_data_stale=True,
        market_data_default_used=True,
        market_data_fallback_used=True,
    ).run({"headline": "QCOM peers up 5%"})
    surface = out["analysis"]["peer_market_validation"]

    assert surface["status"] == "shadow_only"
    assert surface["validated_count"] == 0
    assert surface["rejected_count"] == len(surface["rejected_peer_candidates"])
    assert all(item["validation_reason"] == "missing_market_data" for item in surface["rejected_peer_candidates"])
    assert all(item["reject_reason"] == "missing_market_data" for item in surface["rejected_peer_candidates"])
    assert all(item["status"] == "rejected" for item in surface["rejected_peer_candidates"])
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]


def test_peer_market_validation_flag_off_omits_surface(tmp_path: Path) -> None:
    out = _runner(tmp_path, market_validation_gate=False).run({"headline": "QCOM peers up 5%"})

    assert "peer_market_validation" not in out["analysis"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
