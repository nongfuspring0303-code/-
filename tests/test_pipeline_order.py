from __future__ import annotations

from pathlib import Path

from full_workflow_runner import FullWorkflowRunner
from edt_module_base import ModuleStatus


class _Obj:
    def __init__(self, data):
        self.data = data
        self.status = ModuleStatus.SUCCESS
        self.errors = []


class _FakeIntel:
    def run(self, payload):
        return {
            "event_object": {
                "event_id": "evt-1",
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
        return _Obj({
            "lifecycle_state": "Active",
            "internal_state": "ACTIVE_TRACK",
            "catalyst_state": "Active",
            "time_scale": "intraday",
            "decay_profile": "medium",
            "stale_event": {
                "is_stale": False,
                "downgrade_applied": False,
                "downgrade_from": None,
                "downgrade_to": None,
                "reason": "not_stale",
                "elapsed_hours": 0,
                "threshold_hours": 0,
            },
        })


class _FakeFatigue:
    def run(self, payload):
        return _Obj({
            "fatigue_final": 10,
            "fatigue_score": 10,
            "fatigue_bucket": "low",
            "watch_mode": False,
            "a_minus_1_discount_factor": 1.0,
        })


class _FakeConduction:
    def run(self, payload):
        return _Obj({
            "confidence": 76,
            "conduction_path": ["a", "b", "c"],
            "sector_impacts": [{"sector": "Technology", "direction": "benefit", "impact_score": 0.6, "confidence": 0.8}],
            "stock_candidates": [{"symbol": "QCOM"}, {"symbol": "AMD"}],
            "mapping_source": "rule",
            "needs_manual_review": False,
        })


class _FakeValidation:
    def run(self, payload):
        return _Obj({
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
        })


class _FakeSemantic:
    def analyze(self, headline, summary):
        return {
            "event_type": "sector",
            "sentiment": "positive",
            "confidence": 82,
            "recommended_chain": "sem_chain",
            "recommended_stocks": ["QCOM"],
            "a0_event_strength": 80,
            "expectation_gap": 60,
            "transmission_candidates": ["semiconductor"],
        }

    def analyze_event(self, headline, summary, semantic_output, event_id, event_time):
        return {
            "event_type": semantic_output.get("event_type", "unknown"),
            "event_time": event_time,
            "evidence_grade": "B",
        }


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
        return _Obj({"trade_type": "avoid", "position_sizing": {"mode": "flat", "note": "advisory_only_human_review"}, "entry_timing": {"window": "none", "trigger": "none"}, "risk_switch": "normal", "stop_condition": {"rule": "none"}, "overnight_allowed": "no"})


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
    return r


def test_pipeline_order_semantic_prepass_before_final_selection(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    out = runner.run({"headline": "QCOM up 5%"})

    stage_rows = []
    lines = (tmp_path / "pipeline_stage.jsonl").read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        import json
        row = json.loads(line)
        stage_rows.append((int(row.get("stage_seq", 0)), row.get("stage")))

    names_in_order = [name for _, name in sorted(stage_rows, key=lambda x: x[0])]
    assert "semantic_prepass" in names_in_order
    assert "conduction_candidate_generation" in names_in_order
    assert "conduction_final_selection" in names_in_order

    assert names_in_order.index("semantic_prepass") < names_in_order.index("conduction_final_selection")

    analysis = out["analysis"]
    assert analysis["v5_shadow"]["enable_v5_shadow_output"] is True
    assert analysis["v5_shadow"]["enable_replace_legacy_output"] is False
    assert analysis["v5_shadow"]["comparison_status"] == "observe_only"
    assert isinstance(analysis["conduction_final_selection"]["final_recommended_stocks"], list)
    assert isinstance(analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"], list)


def test_impl1_shadow_boundary_ignores_replace_legacy_payload(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    out = runner.run(
        {
            "headline": "QCOM up 5%",
            "enable_v5_shadow_output": False,
            "enable_replace_legacy_output": True,
        }
    )

    shadow = out["analysis"]["v5_shadow"]
    assert shadow["enable_v5_shadow_output"] is True
    assert shadow["enable_replace_legacy_output"] is False
    assert shadow["replace_legacy_requested"] is True
    assert shadow["comparison_status"] == "observe_only"


def test_impl1_flags_can_disable_semantic_prepass_and_conduction_split(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    out = runner.run(
        {
            "headline": "QCOM up 5%",
            "enable_semantic_prepass": False,
            "enable_conduction_split": False,
        }
    )

    analysis = out["analysis"]
    assert analysis["v5_shadow"]["enable_semantic_prepass"] is False
    assert analysis["v5_shadow"]["enable_conduction_split"] is False
    assert analysis["semantic_prepass"]["status"] == "disabled"
