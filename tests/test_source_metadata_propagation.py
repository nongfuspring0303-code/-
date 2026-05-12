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
                "event_id": "evt-2",
                "category": "A",
                "severity": "E3",
                "source_rank": "B",
                "headline": payload.get("headline", "AMD jumps"),
                "detected_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "source_rank": {"rank": "B", "needs_escalation": False, "confidence": 0.84},
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
                "stale_event": {
                    "is_stale": False,
                    "downgrade_applied": False,
                    "downgrade_from": None,
                    "downgrade_to": None,
                    "reason": "not_stale",
                    "elapsed_hours": 0,
                    "threshold_hours": 0,
                },
            }
        )


class _FakeFatigue:
    def run(self, payload):
        return _Obj(
            {
                "fatigue_final": 8,
                "fatigue_score": 8,
                "fatigue_bucket": "low",
                "watch_mode": False,
                "a_minus_1_discount_factor": 1.0,
            }
        )


class _FakeConduction:
    def run(self, payload):
        return _Obj(
            {
                "confidence": 73,
                "conduction_path": ["x", "y"],
                "sector_impacts": [
                    {"sector": "Technology", "direction": "benefit", "impact_score": 0.7, "confidence": 0.76}
                ],
                "stock_candidates": [
                    {"symbol": "AMD", "source": "semantic", "confidence": 88, "whether_direct_ticker_mentioned": True},
                    {"symbol": "NVDA", "source": "config", "confidence": 80},
                ],
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
            "confidence": 81,
            "recommended_chain": "sem_chain",
            "recommended_stocks": ["AMD"],
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
        return _Obj(
            {
                "primary_path": {"path_text": "main"},
                "secondary_paths": [],
                "rejected_paths": [],
                "target_sector": ["Technology"],
                "target_leader": ["AMD"],
                "target_etf": [],
                "target_followers": [],
            }
        )


class _FakeSignal:
    def run(self, payload):
        return _Obj({"score": 76, "score_decision": "WATCH", "relative_direction_score": 0.68, "absolute_direction": "positive", "driver_confidence": 0.8, "gap_score": 0.5, "execution_confidence": 0.6})


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


def _runner(tmp_path: Path, *, flags: dict[str, bool]) -> FullWorkflowRunner:
    runner = FullWorkflowRunner(audit_dir=str(tmp_path))
    runner.intel = _FakeIntel()
    runner.lifecycle = _FakeLifecycle()
    runner.fatigue = _FakeFatigue()
    runner.conduction = _FakeConduction()
    runner.validation = _FakeValidation()
    runner.semantic = _FakeSemantic()
    runner.path_adjudicator = _FakePathAdj()
    runner.scorer = _FakeSignal()
    runner.opportunity = _FakeOpportunity()
    runner.execution_suggestion_builder = _FakeExecSug()
    runner.path_quality_evaluator = _FakePathQuality()
    runner.execution = _FakeExecution()
    runner.state_store = _FakeStateStore()
    runner._load_feature_flags = lambda: {
        "enable_v5_shadow_output": True,
        "enable_replace_legacy_output": False,
        "enable_conduction_split": True,
        "enable_semantic_prepass": True,
        "enable_source_metadata_propagation": bool(flags.get("enable_source_metadata_propagation", False)),
        "enable_candidate_envelope": bool(flags.get("enable_candidate_envelope", False)),
    }
    return runner


def test_source_metadata_propagation_enriches_candidate_generation_output(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        flags={
            "enable_source_metadata_propagation": True,
            "enable_candidate_envelope": False,
        },
    )

    out = runner.run({"headline": "AMD jumps on AI demand", "source": "https://www.reuters.com/markets/us/amd"})
    analysis = out["analysis"]
    candidates = analysis["conduction_candidate_generation"]["stock_candidates"]

    assert "candidate_envelope" not in analysis
    assert candidates[0]["event_id"] == "evt-2"
    assert candidates[0]["trace_id"] == "evt-2"
    assert candidates[0]["candidate_origin"] == "rule"
    assert candidates[0]["role"] == "semantic"
    assert candidates[0]["relation"] == "anchor"
    assert candidates[0]["source_rank"] == "B"
    assert candidates[0]["source_rank_confidence"] == 0.84
    assert candidates[0]["source_metadata_status"] == "propagated"

    assert candidates[1]["event_id"] == "evt-2"
    assert candidates[1]["candidate_origin"] == "rule"
    assert candidates[1]["role"] == "template"
    assert candidates[1]["relation"] == "template"

    assert out["execution"]["final"]["action"] == "WATCH"
    assert "candidate_envelope" not in out["execution"]


def test_source_metadata_flag_off_keeps_legacy_candidate_shape(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        flags={
            "enable_source_metadata_propagation": False,
            "enable_candidate_envelope": False,
        },
    )

    out = runner.run({"headline": "AMD jumps on AI demand", "source": "https://www.reuters.com/markets/us/amd"})
    candidates = out["analysis"]["conduction_candidate_generation"]["stock_candidates"]

    assert "event_id" not in candidates[0]
    assert "candidate_origin" not in candidates[0]
    assert "role" not in candidates[0]
    assert "relation" not in candidates[0]
    assert "source_metadata_status" not in candidates[0]
    assert out["analysis"]["opportunity_update"]["opportunities"] == []
