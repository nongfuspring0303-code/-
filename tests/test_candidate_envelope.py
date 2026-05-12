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
                "event_id": "evt-1",
                "category": "A",
                "severity": "E3",
                "source_rank": "A",
                "headline": payload.get("headline", "QCOM jumps"),
                "detected_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "source_rank": {"rank": "A", "needs_escalation": False, "confidence": 0.95},
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
                "sector_impacts": [
                    {"sector": "Technology", "direction": "benefit", "impact_score": 0.6, "confidence": 0.8}
                ],
                "stock_candidates": [
                    {"symbol": "QCOM", "source": "tier1_ticker_pool", "confidence": 88, "whether_direct_ticker_mentioned": True},
                    {"symbol": "QCOM", "source": "config", "confidence": 82, "source_sector": "semiconductors"},
                    {"symbol": "BROKEN", "confidence": 61},
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


def test_candidate_envelope_shadow_surface_preserves_same_ticker_provenance(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        flags={
            "enable_source_metadata_propagation": True,
            "enable_candidate_envelope": True,
        },
    )

    out = runner.run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    analysis = out["analysis"]

    assert "candidate_envelope" in analysis
    envelope = analysis["candidate_envelope"]
    assert envelope["status"] == "shadow_only"
    assert envelope["compatibility_surface"] == "candidate_envelope"
    assert envelope["event_id"] == "evt-1"
    assert envelope["source_rank"]["rank"] == "A"
    assert envelope["candidate_count"] == 2

    envelopes = envelope["envelopes"]
    qcom = next(item for item in envelopes if item["symbol"] == "QCOM")
    broken = next(item for item in envelopes if item["symbol"] == "BROKEN")

    assert qcom["source"] == "tier1_ticker_pool"
    assert qcom["role"] in {"ticker_pool", "config"}
    assert qcom["relation"] in {"anchor", "ticker_pool"}
    assert qcom["event_id"] == "evt-1"
    assert qcom["candidate_origin"] == "rule"
    assert qcom["source_rank"] == "A"
    assert qcom["source_rank_confidence"] == 0.95
    assert len(qcom["provenance"]) == 2
    assert {p["source"] for p in qcom["provenance"]} == {"tier1_ticker_pool", "config"}

    assert broken["status"] == "rejected"
    assert broken["reject_reason"] == "missing_critical_provenance"

    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "QCOM", "BROKEN"]
    assert analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"] == ["QCOM", "QCOM", "BROKEN"]


def test_candidate_envelope_flag_off_keeps_legacy_surface_only(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        flags={
            "enable_source_metadata_propagation": False,
            "enable_candidate_envelope": False,
        },
    )

    out = runner.run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    analysis = out["analysis"]

    assert "candidate_envelope" not in analysis
    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "QCOM", "BROKEN"]
    assert analysis["v5_shadow"]["comparison_status"] == "observe_only"
