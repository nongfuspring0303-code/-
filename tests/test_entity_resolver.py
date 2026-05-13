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
                "event_id": "evt-3",
                "category": "A",
                "severity": "E3",
                "source_rank": "A",
                "headline": payload.get("headline", "QCOM jumps"),
                "detected_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "source_rank": {"rank": "A", "needs_escalation": False, "confidence": 0.93},
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
    def __init__(self, stock_candidates):
        self._stock_candidates = list(stock_candidates)

    def run(self, payload):
        return _Obj(
            {
                "confidence": 76,
                "conduction_path": ["a", "b", "c"],
                "sector_impacts": [
                    {"sector": "Technology", "direction": "benefit", "impact_score": 0.6, "confidence": 0.8}
                ],
                "stock_candidates": list(self._stock_candidates),
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


class _FakeExecSug:
    def run(self, payload):
        return _Obj(
            {
                "trade_type": "avoid",
                "position_sizing": {"mode": "flat", "note": "advisory_only_human_review"},
                "entry_timing": {"window": "none", "trigger": "none"},
                "risk_switch": "normal",
                "stop_condition": {"rule": "none"},
                "overnight_allowed": "no",
            }
        )


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
    stock_candidates: list[dict[str, object]],
    enable_entity_resolver: bool,
    enable_candidate_envelope: bool,
    enable_source_metadata_propagation: bool = True,
    alias_registry: tuple[dict[str, str], set[str]] | None = None,
) -> FullWorkflowRunner:
    runner = FullWorkflowRunner(audit_dir=str(tmp_path))
    runner.intel = _FakeIntel()
    runner.lifecycle = _FakeLifecycle()
    runner.fatigue = _FakeFatigue()
    runner.conduction = _FakeConduction(stock_candidates)
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
        "enable_source_metadata_propagation": enable_source_metadata_propagation,
        "enable_candidate_envelope": enable_candidate_envelope,
        "enable_entity_resolver": enable_entity_resolver,
    }
    if alias_registry is not None:
        runner._load_entity_alias_registry = lambda: alias_registry
    return runner


def _qcom_candidates() -> list[dict[str, object]]:
    return [
        {
            "symbol": " qcom ",
            "source": "tier1_ticker_pool",
            "role": "anchor",
            "relation": "anchor",
            "event_id": "evt-3",
            "candidate_origin": "rule",
        },
        {
            "symbol": "QCOM",
            "source": "config",
            "role": "template",
            "relation": "template",
            "event_id": "evt-3",
            "candidate_origin": "rule",
        },
        {
            "symbol": "",
            "source": "tier1_ticker_pool",
            "role": "anchor",
            "relation": "anchor",
            "event_id": "evt-3",
            "candidate_origin": "rule",
        },
    ]


def test_entity_resolver_strips_and_upcases_symbol_and_keeps_shadow_surface(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=_qcom_candidates(),
        enable_entity_resolver=True,
        enable_candidate_envelope=True,
        enable_source_metadata_propagation=True,
    )

    out = runner.run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    analysis = out["analysis"]

    assert "entity_resolution" in analysis
    entity = analysis["entity_resolution"]
    assert entity["status"] == "shadow_only"
    assert entity["compatibility_surface"] == "entity_resolution"
    assert entity["input_surface"] == "conduction_candidate_generation"
    assert entity["event_id"] == "evt-3"
    assert entity["source_rank"]["rank"] == "A"

    entries = entity["entries"]
    qcom_entries = [item for item in entries if item["canonical_symbol"] == "QCOM" and item["resolver_status"] == "resolved"]
    assert len(qcom_entries) == 2
    assert {item["original_symbol"] for item in qcom_entries} == {"qcom", "QCOM"}

    first = next(item for item in qcom_entries if item["original_symbol"] == "qcom")
    assert first["symbol"] == "QCOM"
    assert first["canonical_symbol"] == "QCOM"
    assert first["candidate_origin"] == "rule"
    assert first["source"] == "tier1_ticker_pool"
    assert first["role"] == "anchor"
    assert first["relation"] == "anchor"
    assert first["event_id"] == "evt-3"
    assert first["provenance"]
    assert first["provenance"][0]["source"] == "tier1_ticker_pool"
    assert first["provenance"][0]["role"] == "anchor"

    broken = next(item for item in entries if item["resolver_status"] == "rejected")
    assert broken["reject_reason"] == "missing_symbol"
    assert broken["original_symbol"] == ""
    assert broken["symbol"] == ""
    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM"]
    assert analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"] == ["QCOM"]

    baseline = _runner(
        tmp_path / "baseline",
        stock_candidates=_qcom_candidates(),
        enable_entity_resolver=False,
        enable_candidate_envelope=True,
        enable_source_metadata_propagation=True,
    ).run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    assert baseline["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM"]
    assert baseline["analysis"]["v5_shadow"]["v5_shadow_final_recommended_stocks"] == ["QCOM"]
    assert out["execution"]["final"]["action"] == "WATCH"
    assert "entity_resolution" not in out["execution"]


def test_entity_resolver_invalid_symbol_rejected_and_flag_off_keeps_legacy_behavior(tmp_path: Path) -> None:
    stock_candidates = [
        {
            "symbol": "BAD SYMBOL",
            "source": "semantic",
            "role": "peer",
            "relation": "peer",
            "event_id": "evt-3",
            "candidate_origin": "rule",
        }
    ]
    runner_on = _runner(
        tmp_path,
        stock_candidates=stock_candidates,
        enable_entity_resolver=True,
        enable_candidate_envelope=False,
        enable_source_metadata_propagation=False,
    )
    out_on = runner_on.run({"headline": "Bad symbol headline", "source": "https://example.com/bad"})
    entity = out_on["analysis"]["entity_resolution"]["entries"][0]

    assert entity["resolver_status"] == "rejected"
    assert entity["reject_reason"] == "invalid_symbol"
    assert entity["original_symbol"] == "BAD SYMBOL"
    assert out_on["analysis"]["entity_resolution"]["status"] == "shadow_only"
    assert out_on["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == []
    assert out_on["analysis"]["v5_shadow"]["v5_shadow_final_recommended_stocks"] == []

    runner_off = _runner(
        tmp_path / "off",
        stock_candidates=stock_candidates,
        enable_entity_resolver=False,
        enable_candidate_envelope=False,
        enable_source_metadata_propagation=False,
    )
    out_off = runner_off.run({"headline": "Bad symbol headline", "source": "https://example.com/bad"})
    assert "entity_resolution" not in out_off["analysis"]
    assert out_off["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["BAD SYMBOL"]
    assert out_off["analysis"]["v5_shadow"]["v5_shadow_final_recommended_stocks"] == ["BAD SYMBOL"]
    assert out_on["execution"]["final"]["action"] == "WATCH"
    assert out_off["execution"]["final"]["action"] == "WATCH"


def test_entity_resolver_respects_candidate_envelope_rejected_boundary(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=[
            {
                "symbol": "QCOM",
                "role": "anchor",
                "relation": "anchor",
                "event_id": "evt-3",
                "candidate_origin": "rule",
            }
        ],
        enable_entity_resolver=True,
        enable_candidate_envelope=True,
        enable_source_metadata_propagation=True,
    )

    out = runner.run({"headline": "QCOM headline", "source": "https://example.com/qcom"})
    entity = out["analysis"]["entity_resolution"]["entries"][0]
    envelope = next(item for item in out["analysis"]["candidate_envelope"]["envelopes"] if item["symbol"] == "QCOM")

    assert envelope["status"] == "rejected"
    assert envelope["reject_reason"] == "missing_source"
    assert entity["resolver_status"] == "rejected"
    assert entity["reject_reason"] == "missing_source"
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == []
    assert out["analysis"]["v5_shadow"]["v5_shadow_final_recommended_stocks"] == []


def test_entity_resolver_registry_hook_marks_ambiguous_alias_conflict_non_final(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=[
            {
                "symbol": "ALIASX",
                "source": "semantic",
                "role": "peer",
                "relation": "peer",
                "event_id": "evt-3",
                "candidate_origin": "rule",
            }
        ],
        enable_entity_resolver=True,
        enable_candidate_envelope=False,
        enable_source_metadata_propagation=False,
        alias_registry=({"ALIASX": "AAA"}, {"ALIASX"}),
    )

    out = runner.run({"headline": "Alias conflict headline", "source": "https://example.com/alias"})
    entity = out["analysis"]["entity_resolution"]["entries"][0]

    # This uses an injected alias registry hook; it verifies scaffold behavior,
    # not the default runtime path.
    assert entity["resolver_status"] == "ambiguous"
    assert entity["reject_reason"] == "ambiguous_identity"
    assert entity["canonical_symbol"] == "ALIASX"
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == []
    assert out["analysis"]["v5_shadow"]["v5_shadow_final_recommended_stocks"] == []


def test_entity_resolver_registry_hook_marks_not_found_non_final(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=[
            {
                "symbol": "UNKNOWNX",
                "source": "semantic",
                "role": "peer",
                "relation": "peer",
                "event_id": "evt-3",
                "candidate_origin": "rule",
            }
        ],
        enable_entity_resolver=True,
        enable_candidate_envelope=False,
        enable_source_metadata_propagation=False,
        alias_registry=({"KNOWN": "KNOWN"}, set()),
    )

    out = runner.run({"headline": "Unknown symbol headline", "source": "https://example.com/unknown"})
    entity = out["analysis"]["entity_resolution"]["entries"][0]

    # This uses an injected alias registry hook; it verifies scaffold behavior,
    # not the default runtime path.
    assert entity["resolver_status"] == "not_found"
    assert entity["reject_reason"] == "not_found"
    assert entity["canonical_symbol"] == "UNKNOWNX"
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == []
    assert out["analysis"]["v5_shadow"]["v5_shadow_final_recommended_stocks"] == []


def test_entity_resolver_default_registry_path_does_not_claim_ambiguous_or_not_found(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=[
            {
                "symbol": "UNKNOWNX",
                "source": "semantic",
                "role": "peer",
                "relation": "peer",
                "event_id": "evt-3",
                "candidate_origin": "rule",
            }
        ],
        enable_entity_resolver=True,
        enable_candidate_envelope=False,
        enable_source_metadata_propagation=False,
    )

    out = runner.run({"headline": "Unknown symbol headline", "source": "https://example.com/unknown"})
    entity = out["analysis"]["entity_resolution"]["entries"][0]

    assert entity["resolver_status"] == "resolved"
    assert entity["canonical_symbol"] == "UNKNOWNX"
    assert out["analysis"]["entity_resolution"]["ambiguous_count"] == 0
    assert out["analysis"]["entity_resolution"]["not_found_count"] == 0
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["UNKNOWNX"]
