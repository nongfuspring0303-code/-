#!/usr/bin/env python3
"""
Full-chain runner: Intel -> Analysis -> Execution.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conduction_mapper import ConductionMapper
from fatigue_calculator import FatigueCalculator
from ai_semantic_analyzer import SemanticAnalyzer
from intel_modules import IntelPipeline
from lifecycle_manager import LifecycleManager
from market_validator import MarketValidator
from opportunity_score import OpportunityScorer
from signal_scorer import SignalScorer
from state_store import EventStateStore
from workflow_runner import WorkflowRunner
from transmission_engine.core.path_adjudicator import PathAdjudicator


class FullWorkflowRunner:
    """End-to-end runner across all implemented layers."""

    def __init__(self, config_path: str | None = None, state_db_path: str | None = None):
        self.intel = IntelPipeline()
        self.lifecycle = LifecycleManager(config_path=config_path)
        self.state_store = EventStateStore(db_path=state_db_path)

        fatigue_config_path = Path(__file__).resolve().parent.parent / "configs" / "fatigue_config.yaml"
        self.fatigue = FatigueCalculator(config_path=str(fatigue_config_path), state_store=self.state_store)
        self.conduction = ConductionMapper(config_path=config_path)
        self.validation = MarketValidator(config_path=config_path)
        self.semantic = SemanticAnalyzer(config_path=config_path)
        self.path_adjudicator = PathAdjudicator(config_path=config_path)
        self.scorer = SignalScorer(config_path=config_path)
        self.opportunity = OpportunityScorer()
        self.execution = WorkflowRunner()
        self.config_path = config_path

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        intel_out = self.intel.run(payload)

        event_object = intel_out["event_object"]
        source_rank = intel_out["source_rank"]
        event_id = event_object["event_id"]

        prev_state = self.state_store.get_state(event_id)
        previous_lifecycle = prev_state["lifecycle_state"] if prev_state else None
        previous_internal = prev_state["internal_state"] if prev_state else None
        retry_count = prev_state["retry_count"] if prev_state else 0

        lifecycle_out = self.lifecycle.run(
            {
                "event_id": event_object["event_id"],
                "category": event_object["category"],
                "severity": event_object["severity"],
                "source_rank": event_object["source_rank"],
                "headline": event_object["headline"],
                "detected_at": event_object["detected_at"],
                "is_official_confirmed": payload.get("is_official_confirmed", source_rank["rank"] in ("A", "B")),
                "market_validated": payload.get("market_validated", True),
                "has_material_update": payload.get("has_material_update", True),
                "elapsed_hours": payload.get("elapsed_hours", 2),
                "previous_lifecycle_state": previous_lifecycle,
                "previous_internal_state": previous_internal,
                "retry_count": retry_count,
            }
        ).data

        fatigue_out = self.fatigue.run(
            {
                "event_id": event_object["event_id"],
                "category": event_object["category"],
                "lifecycle_state": lifecycle_out["lifecycle_state"],
                "narrative_tags": payload.get("narrative_tags", ["macro_event"]),
                "category_active_count": payload.get("category_active_count", 3),
                "tag_active_counts": payload.get("tag_active_counts", {"macro_event": 2}),
                "days_since_last_dead": payload.get("days_since_last_dead", 5),
            }
        ).data

        conduction_out = self.conduction.run(
            {
                "event_id": event_object["event_id"],
                "category": event_object["category"],
                "severity": event_object["severity"],
                "headline": event_object["headline"],
                "summary": payload.get("summary", event_object["headline"]),
                "lifecycle_state": lifecycle_out["lifecycle_state"],
                "narrative_tags": payload.get("narrative_tags", ["macro_event"]),
                "policy_intervention": payload.get("policy_intervention", "NONE"),
            }
        ).data

        validation_out = self.validation.run(
            {
                "event_id": event_object["event_id"],
                "conduction_output": {"conduction_path": conduction_out["conduction_path"]},
                "price_changes": payload.get("price_changes", {"SPY": -1.2}),
                "volume_changes": payload.get("volume_changes", {"SPY": 1.8}),
                "cross_asset_linkage": payload.get("cross_asset_linkage", {"confirmed": True}),
                "persistence_minutes": payload.get("persistence_minutes", 90),
                "winner_loser_dispersion": payload.get("winner_loser_dispersion", {"confirmed": True}),
                "market_timestamp": payload.get("market_timestamp", event_object["updated_at"]),
            }
        ).data

        semantic_out = self.semantic.analyze(event_object["headline"], payload.get("summary", event_object["headline"]))
        event_contract = self.semantic.analyze_event(
            event_object["headline"],
            payload.get("summary", event_object["headline"]),
            semantic_output=semantic_out,
            event_id=event_object["event_id"],
            event_time=event_object.get("detected_at", event_object.get("updated_at", "")),
        )

        transmission_paths = [
            {
                "path_id": "p1-main",
                "path_name": " > ".join(conduction_out.get("conduction_path", [])[:3]) or "main_path",
                "path_type": "fundamental",
                "confidence": float(conduction_out.get("confidence", 70)),
                "horizon": "1-5D",
                "persistence": "medium",
            },
            {
                "path_id": "p2-alt",
                "path_name": str(semantic_out.get("recommended_chain", "semantic_alt")),
                "path_type": "asset_pricing",
                "confidence": max(0.0, float(conduction_out.get("confidence", 70)) - 8.0),
                "horizon": "1-3D",
                "persistence": "short",
            },
        ]
        path_out = self.path_adjudicator.run(
            {
                "transmission_paths": transmission_paths,
                "target_sector": [s.get("sector") for s in conduction_out.get("sector_impacts", []) if s.get("sector")],
                "target_leader": [s.get("symbol") for s in conduction_out.get("stock_candidates", []) if s.get("symbol")][:2],
            }
        ).data

        signal_out = self.scorer.run(
            {
                "event_id": event_object["event_id"],
                "severity": event_object["severity"],
                "A0": payload.get("A0", intel_out["severity"]["A0"]),
                "A-1": payload.get("A-1", 65),
                "A1": validation_out["A1"],
                "A1.5": payload.get("A1.5", 58),
                "A0.5": payload.get("A0.5", 0),
                "fatigue_final": fatigue_out["fatigue_final"],
                "a_minus_1_discount_factor": fatigue_out["a_minus_1_discount_factor"],
                "correlation": payload.get("validation_correlation", 0.55),
                "is_crowded": payload.get("is_crowded", False),
                "narrative_mode": payload.get("narrative_mode", "Fact-Driven"),
                "policy_intervention": payload.get("policy_intervention", "NONE"),
                "base_direction": payload.get("direction", "long"),
                "watch_mode": fatigue_out["watch_mode"],
                "weights_version": "score_v1",
            }
        ).data

        analysis_out = {
            "lifecycle": lifecycle_out,
            "fatigue": fatigue_out,
            "conduction": conduction_out,
            "market_validation": validation_out,
            "semantic": semantic_out,
            "event_object_contract": event_contract,
            "path_adjudication": path_out,
            "signal": signal_out,
        }

        sectors = []
        for item in conduction_out.get("sector_impacts", []):
            sectors.append(
                {
                    "name": item.get("sector", "未知板块"),
                    "direction": "LONG" if item.get("direction") == "benefit" else "SHORT",
                    "impact_score": round(min(1.0, max(0.0, float(validation_out.get("A1", 0)) / 100.0)), 2),
                    "confidence": round(min(1.0, max(0.0, float(conduction_out.get("confidence", 0)) / 100.0)), 2),
                }
            )

        opportunity_update = self.opportunity.build_opportunity_update(
            {
                "trace_id": event_object["event_id"],
                "schema_version": "v1.0",
                "sectors": sectors,
                "stock_candidates": conduction_out.get("stock_candidates", []),
                "timestamp": payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
            }
        )
        analysis_out["opportunity_update"] = opportunity_update

        execution_in = {
            "A0": payload.get("A0", intel_out["severity"]["A0"]),
            "A-1": payload.get("A-1", 65),
            "A1": analysis_out["market_validation"]["A1"],
            "A1.5": payload.get("A1.5", 58),
            "A0.5": payload.get("A0.5", 0),
            "severity": intel_out["event_object"]["severity"],
            "fatigue_index": analysis_out["fatigue"]["fatigue_final"],
            "event_state": analysis_out["lifecycle"]["lifecycle_state"],
            "a1_market_validation": validation_out.get("a1_market_validation"),
            "event_type": event_contract.get("event_type", "unknown"),
            "event_time": event_contract.get("event_time", ""),
            "event_name": event_object.get("headline", event_object["event_id"]),
            "evidence_grade": event_contract.get("evidence_grade", "C"),
            "primary_path": path_out.get("primary_path", {}).get("path_text", "undetermined"),
            "secondary_paths": [p.get("path_text", "") for p in path_out.get("secondary_paths", [])],
            "rejected_paths": path_out.get("rejected_paths", []),
            "sector_confirmation": validation_out.get("sector_confirmation", "weak"),
            "leader_confirmation": validation_out.get("leader_confirmation", "unconfirmed"),
            "macro_confirmation": validation_out.get("macro_confirmation", "neutral"),
            "macro_state": (
                "risk-on"
                if validation_out.get("macro_confirmation") == "supportive"
                else "risk-off" if validation_out.get("macro_confirmation") == "hostile" else "mixed"
            ),
            "target_leader": path_out.get("target_leader", []),
            "target_etf": path_out.get("target_etf", []),
            "target_sector": path_out.get("target_sector", []),
            "target_followers": path_out.get("target_followers", []),
            "correlation": payload.get("execution_correlation", 0.55),
            "vix": payload.get("vix"),
            "ted": payload.get("ted"),
            "spread_pct": payload.get("spread_pct"),
            "account_equity": payload.get("account_equity", 100000),
            "entry_price": payload.get("entry_price", 100.0),
            "risk_per_share": payload.get("risk_per_share", 2.0),
            "direction": payload.get("direction", "long"),
            "source_rank": event_object["source_rank"],
            "needs_escalation": source_rank.get("needs_escalation", False),
            "policy_intervention": payload.get("policy_intervention", "NONE"),
            "require_human_confirm": payload.get("require_human_confirm", False),
            "human_confirmed": payload.get("human_confirmed", False),
        }
        execution_out = self.execution.run(execution_in)

        self.state_store.upsert_state(event_id, {
            "internal_state": lifecycle_out["internal_state"],
            "lifecycle_state": lifecycle_out["lifecycle_state"],
            "catalyst_state": lifecycle_out["catalyst_state"],
            "retry_count": retry_count + 1,
            "metadata": {
                "category": event_object["category"],
            },
        })

        return {"intel": intel_out, "analysis": analysis_out, "execution": execution_out}


if __name__ == "__main__":
    sample = {
        "headline": "Fed announces emergency liquidity action after tariff shock",
        "source": "https://www.reuters.com/markets/us/example",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": 28,
        "vix_change_pct": 25,
        "spx_move_pct": 2.2,
        "sector_move_pct": 4.1,
        "sequence": 1,
        "account_equity": 150000,
        "entry_price": 42.5,
        "risk_per_share": 1.5,
        "direction": "long",
    }
    out = FullWorkflowRunner().run(sample)
    print(json.dumps(out, indent=2, ensure_ascii=False))
