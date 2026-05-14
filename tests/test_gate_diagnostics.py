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
    def __init__(self, verdict: str = "long", sentiment: str = "positive", confidence: float = 82.0):
        self.verdict = verdict
        self.sentiment = sentiment
        self.confidence = confidence

    def analyze(self, headline, summary):
        return {
            "event_type": "sector",
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "verdict": self.verdict,
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


def _runner(
    tmp_path: Path,
    *,
    enable_gate_diagnostics: bool = True,
    enable_output_adapter: bool = True,
    enable_path_lite: bool = True,
    enable_semantic_verdict_fix: bool = True,
    verdict: str = "long",
    sentiment: str = "positive",
    confidence: float = 82.0,
) -> FullWorkflowRunner:
    r = FullWorkflowRunner(audit_dir=str(tmp_path))
    r.intel = _FakeIntel()
    r.lifecycle = _FakeLifecycle()
    r.fatigue = _FakeFatigue()
    r.conduction = _FakeConduction()
    r.validation = _FakeValidation()
    r.semantic = _FakeSemantic(verdict=verdict, sentiment=sentiment, confidence=confidence)
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
        "enable_output_adapter_v5": enable_output_adapter,
        "enable_gate_diagnostics": enable_gate_diagnostics,
    }
    return r


def _gate(surface, gate_name: str):
    for item in surface["gate_diagnostics"]:
        if item["gate_name"] == gate_name:
            return item
    raise AssertionError(f"missing gate {gate_name}")


def test_gate_diagnostics_surface_is_advisory_only_and_auditable(tmp_path: Path) -> None:
    out = _runner(tmp_path).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["gate_diagnostics"]

    assert surface["status"] == "advisory_only"
    assert surface["compatibility_surface"] == "gate_diagnostics"
    assert surface["compatibility_only"] is True
    assert surface["output_authority"] == "advisory_only"
    assert surface["allows_final_selection"] is False
    assert surface["allows_execution"] is False
    assert surface["allows_broker_action"] is False
    assert surface["final_action_allowed"] is False
    assert surface["production_authority"] is False
    assert surface["release_status"] == "observe_only"
    assert surface["requires_downstream_adjudication"] is True
    assert surface["overall_status"] == "pass"
    assert surface["gate_count"] == 2
    assert "path_adjudication_lite" in surface["source_surfaces"]
    assert "output_adapter_v5" in surface["source_surfaces"]
    path_gate = _gate(surface, "path_adjudication_lite")
    adapter_gate = _gate(surface, "output_adapter_v5")
    assert path_gate["gate_status"] == "pass"
    assert path_gate["source_surface"] == "path_adjudication_lite"
    assert path_gate["trace_id"] == surface["trace_id"]
    assert adapter_gate["gate_status"] == "pass"
    assert adapter_gate["source_surface"] == "output_adapter_v5"
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_gate_diagnostics_flag_off_omits_surface(tmp_path: Path) -> None:
    out = _runner(tmp_path, enable_gate_diagnostics=False).run({"headline": "QCOM jumps"})
    assert "gate_diagnostics" not in out["analysis"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_gate_diagnostics_no_sources_does_not_pass(tmp_path: Path) -> None:
    out = _runner(
        tmp_path,
        enable_gate_diagnostics=True,
        enable_output_adapter=False,
        enable_path_lite=False,
        enable_semantic_verdict_fix=False,
    ).run({"headline": "QCOM jumps"})
    surface = out["analysis"]["gate_diagnostics"]
    assert surface["gate_count"] == 0
    assert surface["overall_status"] == "manual_review"
    assert surface["overall_status"] != "pass"
    assert surface["overall_reason"] == "no_gate_diagnostic_sources_available"
    assert surface["requires_human_review"] is True
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_gate_diagnostics_can_escalate_manual_review_from_path_adjudication(tmp_path: Path) -> None:
    out = _runner(tmp_path, verdict="abstain", sentiment="neutral").run({"headline": "QCOM jumps"})
    surface = out["analysis"]["gate_diagnostics"]
    path_gate = _gate(surface, "path_adjudication_lite")

    assert surface["overall_status"] == "manual_review"
    assert surface["overall_reason"] == "manual_review_gate_detected"
    assert surface["requires_human_review"] is True
    assert path_gate["gate_status"] == "manual_review"
    assert path_gate["reason"] == "semantic_abstain_requires_manual_review"
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]


def test_gate_diagnostics_can_report_output_adapter_downgrade(tmp_path: Path) -> None:
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
    surface = out["analysis"]["gate_diagnostics"]
    adapter_gate = _gate(surface, "output_adapter_v5")

    assert surface["overall_status"] == "downgrade"
    assert surface["overall_reason"] == "downgrade_gate_detected"
    assert surface["requires_human_review"] is False
    assert adapter_gate["gate_status"] == "downgrade"
    assert adapter_gate["reason"] == "adapter_mutation_detected"
    assert out["analysis"]["output_adapter"]["adapter_mode"] == "downgraded_fail_closed"


def test_gate_diagnostics_block_status_is_reachable_and_dominates(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    def _forced_path_surface(
        *,
        semantic_prepass,
        semantic_verdict_fix_out,
        path_out,
        conduction_out,
        trace_id,
        event_id,
    ):
        return {
            "status": "shadow_only",
            "compatibility_surface": "path_adjudication_lite",
            "compatibility_only": True,
            "trace_id": trace_id,
            "event_id": event_id,
            "output_authority": "shadow_only",
            "allows_final_selection": False,
            "allows_execution": False,
            "final_recommendation_allowed": False,
            "production_authority": False,
            "release_status": "observe_only",
            "requires_downstream_adjudication": True,
            "final_path": "unsupported_path",
            "decision_reason": "unsupported_path",
            "non_final": True,
        }

    runner._build_path_adjudicator_lite_surface = _forced_path_surface  # type: ignore[assignment]
    out = runner.run({"headline": "QCOM jumps"})
    surface = out["analysis"]["gate_diagnostics"]
    path_gate = _gate(surface, "path_adjudication_lite")

    assert path_gate["gate_status"] == "block"
    assert surface["overall_status"] == "block"
    assert surface["overall_reason"] == "blocking_gate_detected"
    assert surface["overall_status"] != "pass"
    assert surface["overall_status"] != "manual_review"
    assert surface["overall_status"] != "downgrade"
    assert surface["requires_human_review"] is True
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM", "AMD", "NVDA"]
    assert out["execution"]["final"]["action"] == "WATCH"
