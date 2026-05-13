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
                "event_id": "evt-4",
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
        return _Obj({"lifecycle_state": "Active", "internal_state": "ACTIVE_TRACK", "catalyst_state": "Active", "time_scale": "intraday", "decay_profile": "medium", "stale_event": {"is_stale": False}})


class _FakeFatigue:
    def run(self, payload):
        return _Obj({"fatigue_final": 10, "fatigue_score": 10, "fatigue_bucket": "low", "watch_mode": False, "a_minus_1_discount_factor": 1.0})


class _FakeConduction:
    def run(self, payload):
        return _Obj({"confidence": 76, "conduction_path": ["a", "b", "c"], "sector_impacts": [{"sector": "Technology", "direction": "benefit", "impact_score": 0.6, "confidence": 0.8}], "stock_candidates": [{"symbol": "QCOM"}, {"symbol": "AMD"}, {"symbol": "NVDA"}], "mapping_source": "rule", "needs_manual_review": False})


class _FakeValidation:
    def run(self, payload):
        return _Obj({"A1": 74, "checks": [], "a1_market_validation": "pass", "market_data_source": "payload_direct", "market_data_present": True, "market_data_stale": False, "market_data_default_used": False, "market_data_fallback_used": False, "sector_confirmation": "strong", "leader_confirmation": "confirmed", "macro_confirmation": "supportive"})


class _FakeSemantic:
    def analyze(self, headline, summary):
        return {"event_type": "sector", "sentiment": "positive", "confidence": 88, "recommended_chain": "sem_chain", "recommended_stocks": ["QCOM", "AMD", "AVGO"], "a0_event_strength": 80, "expectation_gap": 60, "transmission_candidates": ["semiconductor"]}

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


def _runner(tmp_path: Path) -> FullWorkflowRunner:

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
        "enable_semantic_full_peer_expansion": True,
    }
    return r


def test_peer_candidate_prompt_contract_fields_and_evidence(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM up 5%"})
    surface = out["analysis"]["semantic_full_peer_expansion"]
    contract = surface["prompt_contract"]

    assert contract["schema_version"] == "stage8a.peer_prompt_contract.v1"
    assert contract["relation_evidence_required"] is True
    assert contract["mode"] == "shadow_only"
    assert contract["required_output_fields"] == [
        "symbol",
        "canonical_symbol",
        "peer_symbol",
        "anchor_symbol",
        "relation_type",
        "relation_evidence",
        "relation_evidence_source",
        "event_id",
        "trace_id",
        "candidate_origin",
        "source",
        "source_rank",
        "semantic_confidence",
        "peer_confidence",
        "resolver_status",
        "status",
        "reject_reason",
        "downgrade_reason",
        "is_final",
    ]
    assert contract["relation_evidence_required_fields"] == [
        "evidence_type",
        "evidence_value",
        "evidence_source",
        "evidence_text",
        "confidence",
    ]
    assert contract["peer_validation_input_fields"] == [
        "peer_symbol",
        "anchor_symbol",
        "canonical_symbol",
        "relation_type",
        "relation_evidence",
        "relation_evidence_source",
        "semantic_confidence",
        "peer_confidence",
        "source_rank",
        "event_id",
        "trace_id",
        "candidate_origin",
        "status",
        "reject_reason",
        "downgrade_reason",
        "is_final",
    ]

    for item in surface["peer_candidates"]:
        assert item["status"] == "candidate"
        assert item["non_final"] is True
        assert isinstance(item["symbol"], str) and item["symbol"]
        assert isinstance(item["relation_type"], str) and item["relation_type"]
        assert isinstance(item["canonical_symbol"], str) and item["canonical_symbol"]
        assert isinstance(item["peer_symbol"], str) and item["peer_symbol"]
        assert isinstance(item["anchor_symbol"], str) and item["anchor_symbol"]
        assert isinstance(item["event_id"], str) and item["event_id"]
        assert isinstance(item["trace_id"], str) and item["trace_id"]
        assert isinstance(item["candidate_origin"], str) and item["candidate_origin"]
        assert isinstance(item["source"], str) and item["source"]
        assert isinstance(item["source_rank"], dict)
        assert isinstance(item["semantic_confidence"], float)
        assert isinstance(item["peer_confidence"], float)
        assert item["resolver_status"] == "resolved"
        assert item["reject_reason"] is None
        assert item["downgrade_reason"] is None
        assert item["is_final"] is False
        evidence = item["relation_evidence"]
        assert isinstance(evidence, dict)
        assert evidence["evidence_type"] == "same_sector_peer"
        assert isinstance(evidence.get("evidence_source"), str) and evidence["evidence_source"]
        assert isinstance(evidence.get("evidence_value"), dict)
        assert "semantic_event_type" in evidence["evidence_value"]
        assert "transmission_candidates" in evidence["evidence_value"]
        assert "evidence_text" in evidence
        assert "confidence" in evidence


def test_peer_candidate_prompt_contract_flag_off_keeps_surface_absent(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runner._load_feature_flags = lambda: {
        "enable_v5_shadow_output": True,
        "enable_replace_legacy_output": False,
        "enable_conduction_split": True,
        "enable_semantic_prepass": True,
        "enable_semantic_full_peer_expansion": False,
    }

    out = runner.run({"headline": "QCOM up 5%"})
    assert "semantic_full_peer_expansion" not in out["analysis"]
