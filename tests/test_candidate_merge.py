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
    enable_unified_candidate_pool: bool,
    enable_multisource_merge: bool,
    enable_entity_resolver: bool = True,
    enable_candidate_envelope: bool = True,
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
        "enable_unified_candidate_pool": enable_unified_candidate_pool,
        "enable_multisource_merge": enable_multisource_merge,
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
    ]


def _symbols(items: list[dict[str, object]]) -> list[str]:
    return [str(item.get("canonical_symbol", item.get("symbol", ""))) for item in items]


def test_candidate_merge_merges_same_canonical_symbol_and_preserves_provenance(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=_qcom_candidates(),
        enable_unified_candidate_pool=True,
        enable_multisource_merge=True,
    )

    out = runner.run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    analysis = out["analysis"]

    assert "unified_candidate_pool" in analysis
    pool = analysis["unified_candidate_pool"]
    assert pool["status"] == "shadow_only"
    assert pool["compatibility_surface"] == "unified_candidate_pool"
    assert pool["item_count"] == 1
    assert pool["merged_count"] == 1
    assert pool["rejected_count"] == 0
    assert pool["downgraded_count"] == 0

    item = pool["items"][0]
    assert item["symbol"] == "QCOM"
    assert item["canonical_symbol"] == "QCOM"
    assert item["source_list"] == ["tier1_ticker_pool", "config"]
    assert item["role_list"] == ["anchor", "template"]
    assert item["relation_list"] == ["anchor", "template"]
    assert item["event_ids"] == ["evt-3"]
    assert item["resolver_status"] == "resolved"
    assert item["merge_status"] == "merged"
    assert item["status"] == "candidate"
    assert len(item["provenance"]) == 2
    assert {p["source"] for p in item["provenance"]} == {"tier1_ticker_pool", "config"}

    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM"]
    assert analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"] == ["QCOM"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_candidate_merge_non_final_and_rejected_inputs_remain_non_final(tmp_path: Path) -> None:
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
            },
            {
                "symbol": "UNKNOWNX",
                "source": "semantic",
                "role": "peer",
                "relation": "peer",
                "event_id": "evt-3",
                "candidate_origin": "rule",
            },
            {
                "symbol": "BROKEN",
                "role": "anchor",
                "relation": "anchor",
                "event_id": "evt-3",
                "candidate_origin": "rule",
            },
        ],
        enable_unified_candidate_pool=True,
        enable_multisource_merge=True,
        alias_registry=({"ALIASX": "AAA"}, {"ALIASX"}),
    )

    out = runner.run({"headline": "Mixed symbols headline", "source": "https://example.com/mixed"})
    analysis = out["analysis"]
    pool = analysis["unified_candidate_pool"]

    assert _symbols(pool["items"]) == ["ALIASX", "UNKNOWNX", "BROKEN"]
    alias_item = next(item for item in pool["items"] if item["symbol"] == "ALIASX")
    unknown_item = next(item for item in pool["items"] if item["symbol"] == "UNKNOWNX")
    broken_item = next(item for item in pool["items"] if item["symbol"] == "BROKEN")

    assert alias_item["resolver_status"] == "ambiguous"
    assert alias_item["status"] == "downgraded"
    assert alias_item["merge_status"] == "downgraded"
    assert alias_item["downgrade_reason"] == "ambiguous_identity"

    assert unknown_item["resolver_status"] == "not_found"
    assert unknown_item["status"] == "downgraded"
    assert unknown_item["merge_status"] == "downgraded"
    assert unknown_item["downgrade_reason"] == "not_found"

    assert broken_item["status"] == "rejected"
    assert broken_item["merge_status"] == "rejected"
    assert broken_item["reject_reason"] == "missing_source"

    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == []
    assert analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"] == []
    assert out["execution"]["final"]["action"] == "WATCH"


def test_candidate_merge_flag_off_keeps_legacy_surface_only(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=_qcom_candidates(),
        enable_unified_candidate_pool=False,
        enable_multisource_merge=False,
    )

    out = runner.run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    analysis = out["analysis"]

    assert "unified_candidate_pool" not in analysis
    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM"]
    assert analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"] == ["QCOM"]
    assert out["execution"]["final"]["action"] == "WATCH"


def test_candidate_merge_disable_merge_keeps_same_symbol_provenance_separate(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=_qcom_candidates(),
        enable_unified_candidate_pool=True,
        enable_multisource_merge=False,
    )

    out = runner.run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    pool = out["analysis"]["unified_candidate_pool"]

    assert pool["item_count"] == 2
    assert len([item for item in pool["items"] if item["canonical_symbol"] == "QCOM"]) == 2
    assert pool["merged_count"] == 0
    assert [item["source_list"] for item in pool["items"]] == [["tier1_ticker_pool"], ["config"]]
    assert [item["merge_status"] for item in pool["items"]] == ["unmerged", "unmerged"]
    assert out["analysis"]["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM"]


def test_candidate_merge_missing_entity_resolution_does_not_silently_resolve_or_merge(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        stock_candidates=_qcom_candidates(),
        enable_unified_candidate_pool=True,
        enable_multisource_merge=True,
        enable_entity_resolver=False,
    )

    out = runner.run({"headline": "QCOM up 5%", "source": "https://www.reuters.com/markets/us/qcom"})
    analysis = out["analysis"]
    pool = analysis["unified_candidate_pool"]

    # Without entity_resolution, PR-3C must stay on the safe side of the boundary:
    # source-specific records remain separate and are explicitly marked non-final.
    assert pool["item_count"] == 2
    assert pool["merged_count"] == 0
    assert pool["rejected_count"] == 0
    assert pool["downgraded_count"] == 2
    assert _symbols(pool["items"]) == ["QCOM", "QCOM"]
    assert [item["merge_status"] for item in pool["items"]] == ["downgraded", "downgraded"]
    assert [item["status"] for item in pool["items"]] == ["downgraded", "downgraded"]
    assert [item["resolver_status"] for item in pool["items"]] == ["missing_entity_resolution", "missing_entity_resolution"]
    assert [item["downgrade_reason"] for item in pool["items"]] == ["missing_entity_resolution", "missing_entity_resolution"]
    assert [item["source_list"] for item in pool["items"]] == [["tier1_ticker_pool"], ["config"]]
    assert analysis["conduction_final_selection"]["final_recommended_stocks"] == ["QCOM"]
    assert analysis["v5_shadow"]["v5_shadow_final_recommended_stocks"] == ["QCOM"]
    assert out["execution"]["final"]["action"] == "WATCH"
