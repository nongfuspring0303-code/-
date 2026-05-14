from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
                "event_id": "evt-audit-1",
                "category": "A",
                "severity": "E3",
                "source_rank": "BROKEN_SHOULD_NOT_BE_USED",
                "headline": payload.get("headline", "QCOM jumps"),
                "detected_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "source_rank": {"rank": "A", "needs_escalation": False, "confidence": 0.9},
            # keep dict shape for default runtime path
            "severity": {"A0": 78},
        }


class _FakeLifecycle:
    def __init__(self):
        self.last_payload = None

    def run(self, payload):
        self.last_payload = dict(payload)
        return _Obj(
            {
                "lifecycle_state": "Active",
                "internal_state": "ACTIVE_TRACK",
                "catalyst_state": "Active",
                "stale_event": {"is_stale": False},
            }
        )


class _FakeFatigue:
    def __init__(self):
        self.drop_fatigue_score = False

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
    def build_opportunity_update(self, payload):
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

    def run(self, payload):
        self.last_payload = dict(payload)
        # Mutate incoming sector_impacts to prove conduction_out is isolated from candidate_generation_out.
        sector_impacts = payload.get("sector_impacts")
        if isinstance(sector_impacts, list):
            sector_impacts.append({"sector": "MUTATED", "direction": "watch"})
        return {"final": {"action": "WATCH", "reason": "missing_opportunity"}}


class _FakeStateStore:
    def get_state(self, event_id):
        return None

    def upsert_state(self, event_id, state):
        return None


def _runner(
    tmp_path: Path, *, missing_a1: bool = False
) -> tuple[FullWorkflowRunner, _FakeLifecycle, _FakeFatigue, _CapturingExecutionSuggestion, _MutatingExecution]:
    lifecycle = _FakeLifecycle()
    fatigue = _FakeFatigue()
    execution_suggestion = _CapturingExecutionSuggestion()

    execution = _MutatingExecution()
    r = FullWorkflowRunner(audit_dir=str(tmp_path))
    r.intel = _FakeIntel()
    r.lifecycle = lifecycle
    r.fatigue = fatigue
    r.conduction = _FakeConduction()
    r.validation = _FakeValidation(missing_a1=missing_a1)
    r.semantic = _FakeSemantic()
    r.path_adjudicator = _FakePathAdj()
    r.scorer = _FakeSignal()
    r.opportunity = _FakeOpportunity()
    r.execution_suggestion_builder = execution_suggestion
    r.path_quality_evaluator = _FakePathQuality()
    r.execution = execution
    r.state_store = _FakeStateStore()
    return r, lifecycle, fatigue, execution_suggestion, execution


def test_symbols_requested_none_uses_derived_symbols(tmp_path: Path) -> None:
    runner, _, _, _, _ = _runner(tmp_path)
    out = runner.run(
        {
            "headline": "QCOM jumps",
            "symbols_requested": None,
            "symbols_returned": None,
            "price_changes": {"qcom": 0.05, "amd": 0.03, "nvda": 0.04},
            "volume_changes": {"qcom": 0.10, "amd": 0.07, "nvda": 0.08},
        }
    )
    log_path = Path(runner.market_data_provenance_log_path)
    assert log_path.exists()
    rec = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["symbols_requested"] == ["AMD", "NVDA", "QCOM"]
    assert rec["symbols_returned"] == ["AMD", "NVDA", "QCOM"]


def test_conduction_out_does_not_alias_candidate_generation_output(tmp_path: Path) -> None:
    runner, _, _, _, _ = _runner(tmp_path)
    out = runner.run({"headline": "QCOM jumps"})
    cand_sectors = [x.get("sector") for x in out["analysis"]["conduction_candidate_generation"]["sector_impacts"]]
    # execution.run mutates its input by appending MUTATED; candidate_generation output must remain untouched.
    assert "MUTATED" not in cand_sectors


def test_fatigue_score_falls_back_to_fatigue_final_for_execution_suggestion(tmp_path: Path) -> None:
    runner, _, fatigue, execution_suggestion, _ = _runner(tmp_path)
    fatigue.drop_fatigue_score = True
    runner.run({"headline": "QCOM jumps"})
    assert execution_suggestion.last_payload is not None
    assert execution_suggestion.last_payload["fatigue_score"] == 10


def test_source_rank_for_lifecycle_and_execution_uses_intel_source_rank_object(tmp_path: Path) -> None:
    runner, lifecycle, _, _, execution = _runner(tmp_path)
    runner.run({"headline": "QCOM jumps"})
    assert lifecycle.last_payload is not None
    assert lifecycle.last_payload["source_rank"] == "A"
    assert execution.last_payload is not None
    assert execution.last_payload["source_rank"]["rank"] == "A"
    assert execution.last_payload["source_rank"] != "BROKEN_SHOULD_NOT_BE_USED"


def test_missing_validation_a1_does_not_crash_signal_or_execution_payload(tmp_path: Path) -> None:
    runner, _, _, _, execution = _runner(tmp_path, missing_a1=True)
    out = runner.run({"headline": "QCOM jumps"})
    assert out["analysis"]["signal"]["score"] == 78
    assert execution.last_payload is not None
    assert execution.last_payload["A1"] == 0.0
