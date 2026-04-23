#!/usr/bin/env python3
"""
Full-chain runner: Intel -> Analysis -> Execution.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
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

    def __init__(self, config_path: str | None = None, state_db_path: str | None = None, audit_dir: str | None = None):
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
        self.logs_dir = Path(audit_dir) if audit_dir else ROOT / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.execution = WorkflowRunner(audit_dir=str(self.logs_dir))
        self.config_path = config_path
        self.raw_news_ingest_log_path = self.logs_dir / "raw_news_ingest.jsonl"
        self.market_data_provenance_log_path = self.logs_dir / "market_data_provenance.jsonl"
        self.pipeline_stage_log_path = self.logs_dir / "pipeline_stage.jsonl"
        self.rejected_events_log_path = self.logs_dir / "rejected_events.jsonl"
        self.quarantine_replay_log_path = self.logs_dir / "quarantine_replay.jsonl"
        self.trace_scorecard_log_path = self.logs_dir / "trace_scorecard.jsonl"
        for path in (
            self.raw_news_ingest_log_path,
            self.market_data_provenance_log_path,
            self.pipeline_stage_log_path,
            self.rejected_events_log_path,
            self.quarantine_replay_log_path,
            self.trace_scorecard_log_path,
        ):
            path.touch(exist_ok=True)
        self._evidence_lock = threading.Lock()

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        with self._evidence_lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _log_pipeline_stage(
        self,
        *,
        trace_id: str,
        event_id: str,
        request_id: str | None,
        batch_id: str | None,
        event_hash: str,
        stage_seq: int,
        stage: str,
        status: str,
        details: Dict[str, Any] | None = None,
    ) -> None:
        self._append_jsonl(
            self.pipeline_stage_log_path,
            {
                "logged_at": self._utc_now(),
                "trace_id": trace_id,
                "event_trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "event_id": event_id,
                "event_hash": event_hash,
                "stage_seq": stage_seq,
                "stage": stage,
                "status": status,
                "details": details or {},
            },
        )

    @staticmethod
    def _grade_from_score(score: float) -> str:
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        return "D"

    def _load_sector_whitelist(self) -> set[str]:
        cache = getattr(self, "_sector_whitelist_cache", None)
        if isinstance(cache, set):
            return cache

        whitelist: set[str] = set()
        cfg = ROOT / "configs" / "sector_impact_mapping.yaml"
        if cfg.exists():
            in_mapping = False
            for raw_line in cfg.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("mapping:"):
                    in_mapping = True
                    continue
                if line.startswith("mappings:"):
                    in_mapping = False
                    continue
                if line.startswith("sector:"):
                    value = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if value:
                        whitelist.add(value)
                    continue
                if in_mapping and line.startswith("-"):
                    value = line.lstrip("-").strip().strip('"').strip("'")
                    if value:
                        whitelist.add(value)

        self._sector_whitelist_cache = whitelist
        return whitelist

    @staticmethod
    def _count_placeholders(values: List[Any]) -> tuple[int, int]:
        placeholder_tokens = {"", "unknown", "n/a", "na", "none", "null", "placeholder", "tbd"}
        total = 0
        placeholders = 0
        for value in values:
            text = str(value).strip().lower()
            if not text:
                continue
            total += 1
            if text in placeholder_tokens:
                placeholders += 1
        return placeholders, total

    @staticmethod
    def _build_a_gate_blockers(
        *,
        has_opportunity: bool,
        stale: bool,
        default_used: bool,
        fallback_used: bool,
        final_reason: str,
    ) -> List[str]:
        blockers: List[str] = []
        reason = str(final_reason or "").lower()
        if (not has_opportunity) or ("missing_opportunity" in reason):
            blockers.append("MISSING_OPPORTUNITY")
        if stale or ("market_data_stale" in reason):
            blockers.append("MARKET_DATA_STALE")
        if default_used or ("market_data_default_used" in reason):
            blockers.append("MARKET_DATA_DEFAULT_USED")
        if fallback_used or ("market_data_fallback_used" in reason):
            blockers.append("MARKET_DATA_FALLBACK_USED")
        deduped = sorted(set(blockers))
        return deduped

    def _build_b_side_scores(
        self,
        *,
        trace_id: str,
        event_hash: str,
        final_action: str,
        final_reason: str,
        sector_candidates: List[Any],
        ticker_candidates: List[Any],
        theme_tags: List[Any],
        sectors: List[Dict[str, Any]],
        sector_impacts: List[Dict[str, Any]],
        stock_candidates: List[Dict[str, Any]],
        mapping_source: str,
        needs_manual_review: bool,
        tradeable: Any,
        opportunity_count: Any,
    ) -> Dict[str, Any]:
        whitelist = self._load_sector_whitelist()
        sectors_values = [str(item.get("name", "")).strip() for item in sectors if isinstance(item, dict)]
        non_whitelist_sector_count = (
            sum(1 for name in sectors_values if name and name not in whitelist) if whitelist else 0
        )

        stock_symbol_pool = {
            str(item.get("symbol", "")).strip().upper()
            for item in stock_candidates
            if isinstance(item, dict) and str(item.get("symbol", "")).strip()
        }
        ticker_norm = [str(x).strip().upper() for x in ticker_candidates if str(x).strip()]
        ticker_truth_source_hit = sum(1 for symbol in ticker_norm if symbol in stock_symbol_pool)
        ticker_truth_source_miss = sum(1 for symbol in ticker_norm if symbol not in stock_symbol_pool)

        placeholder_count, placeholder_total = self._count_placeholders(
            list(sector_candidates) + list(ticker_candidates) + list(theme_tags) + [final_reason]
        )
        placeholder_leakage_rate = (
            float(placeholder_count) / float(placeholder_total) if placeholder_total > 0 else 0.0
        )

        sector_hard_fail = non_whitelist_sector_count > 0 or not sectors_values
        ticker_hard_fail = ticker_truth_source_miss > 0 or not ticker_norm
        output_hard_fail = placeholder_leakage_rate > 0.01

        sector_quality_score = 100.0
        if sector_hard_fail:
            sector_quality_score = 0.0
        else:
            if not sector_impacts:
                sector_quality_score -= 40.0
            if not mapping_source:
                sector_quality_score -= 20.0
            sector_quality_score = max(0.0, min(100.0, sector_quality_score))

        ticker_quality_score = 100.0
        if ticker_hard_fail:
            ticker_quality_score = 0.0
        else:
            if not stock_candidates:
                ticker_quality_score -= 40.0
            if ticker_truth_source_hit == 0:
                ticker_quality_score -= 60.0
            ticker_quality_score = max(0.0, min(100.0, ticker_quality_score))

        output_quality_score = 100.0
        if output_hard_fail:
            output_quality_score = 0.0
        else:
            if needs_manual_review:
                output_quality_score -= 15.0
            if not final_action:
                output_quality_score -= 40.0
            if not final_reason:
                output_quality_score -= 40.0
            if not theme_tags:
                output_quality_score -= 20.0
            output_quality_score = max(0.0, min(100.0, output_quality_score))

        mapping_acceptance_score = 100.0
        if sector_hard_fail or ticker_hard_fail or output_hard_fail:
            mapping_acceptance_score = 0.0
        else:
            if not trace_id:
                mapping_acceptance_score -= 40.0
            if not event_hash:
                mapping_acceptance_score -= 40.0
            if opportunity_count is None:
                mapping_acceptance_score -= 20.0
            if tradeable is None:
                mapping_acceptance_score -= 20.0
            mapping_acceptance_score = max(0.0, min(100.0, mapping_acceptance_score))

        b_overall_score = min(
            sector_quality_score,
            ticker_quality_score,
            output_quality_score,
            mapping_acceptance_score,
        )
        b_signoff_ready = bool(
            sector_quality_score >= 80.0
            and ticker_quality_score >= 80.0
            and output_quality_score >= 80.0
            and mapping_acceptance_score >= 80.0
            and b_overall_score >= 80.0
            and not (sector_hard_fail or ticker_hard_fail or output_hard_fail)
        )

        return {
            "mapping_source": mapping_source,
            "needs_manual_review": needs_manual_review,
            "placeholder_count": placeholder_count,
            "placeholder_total": placeholder_total,
            "placeholder_leakage_rate": round(placeholder_leakage_rate, 4),
            "non_whitelist_sector_count": non_whitelist_sector_count,
            "ticker_truth_source_hit": ticker_truth_source_hit,
            "ticker_truth_source_miss": ticker_truth_source_miss,
            "sector_quality_score": round(sector_quality_score, 2),
            "ticker_quality_score": round(ticker_quality_score, 2),
            "output_quality_score": round(output_quality_score, 2),
            "mapping_acceptance_score": round(mapping_acceptance_score, 2),
            "b_overall_score": round(b_overall_score, 2),
            "b_signoff_ready": b_signoff_ready,
        }

    def _build_trace_scorecard(
        self,
        *,
        trace_id: str,
        event_id: str,
        request_id: str | None,
        batch_id: str | None,
        event_hash: str,
        execution_in: Dict[str, Any],
        execution_out: Dict[str, Any],
        conduction_out: Dict[str, Any],
        sectors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        final = execution_out.get("final", {}) if isinstance(execution_out, dict) else {}
        final_action = str(final.get("action", "UNKNOWN")).upper()
        final_reason = str(final.get("reason", ""))
        stale = bool(execution_in.get("market_data_stale", False))
        default_used = bool(execution_in.get("market_data_default_used", False))
        fallback_used = bool(execution_in.get("market_data_fallback_used", False))
        has_opportunity = bool(execution_in.get("has_opportunity", False))
        semantic_event_type = str(execution_in.get("semantic_event_type", "unknown"))
        sector_candidates = execution_in.get("sector_candidates", []) if isinstance(execution_in.get("sector_candidates", []), list) else []
        ticker_candidates = execution_in.get("ticker_candidates", []) if isinstance(execution_in.get("ticker_candidates", []), list) else []
        theme_tags = execution_in.get("theme_tags", []) if isinstance(execution_in.get("theme_tags", []), list) else []
        tradeable = execution_in.get("tradeable")
        opportunity_count = execution_in.get("opportunity_count")
        sector_impacts = conduction_out.get("sector_impacts", []) if isinstance(conduction_out, dict) else []
        stock_candidates = conduction_out.get("stock_candidates", []) if isinstance(conduction_out, dict) else []
        mapping_source = str(conduction_out.get("mapping_source", "")).strip() if isinstance(conduction_out, dict) else ""
        needs_manual_review = bool(conduction_out.get("needs_manual_review", False)) if isinstance(conduction_out, dict) else False

        gate_safety_score = 100.0
        if stale:
            gate_safety_score -= 25.0
        if default_used:
            gate_safety_score -= 35.0
        if fallback_used:
            gate_safety_score -= 20.0
        if final_action == "EXECUTE" and (stale or default_used):
            gate_safety_score -= 20.0
        gate_safety_score = max(0.0, min(100.0, gate_safety_score))

        output_quality_score = 60.0
        if has_opportunity:
            output_quality_score += 15.0
        if semantic_event_type != "unknown":
            output_quality_score += 10.0
        if isinstance(sector_candidates, list) and sector_candidates:
            output_quality_score += 10.0
        if isinstance(ticker_candidates, list) and ticker_candidates:
            output_quality_score += 5.0
        output_quality_score = max(0.0, min(100.0, output_quality_score))

        provider_freshness_score = 100.0
        if stale:
            provider_freshness_score -= 40.0
        if default_used:
            provider_freshness_score -= 35.0
        if fallback_used:
            provider_freshness_score -= 20.0
        provider_freshness_score = max(0.0, min(100.0, provider_freshness_score))

        audit_completeness_score = 0.0
        if trace_id:
            audit_completeness_score += 30.0
        if event_hash:
            audit_completeness_score += 30.0
        if request_id:
            audit_completeness_score += 20.0
        if batch_id:
            audit_completeness_score += 20.0

        total_score = (
            0.35 * gate_safety_score
            + 0.30 * output_quality_score
            + 0.20 * provider_freshness_score
            + 0.15 * audit_completeness_score
        )
        pre_cap_total_score = round(max(0.0, min(100.0, total_score)), 2)
        a_gate_blocker_codes = self._build_a_gate_blockers(
            has_opportunity=has_opportunity,
            stale=stale,
            default_used=default_used,
            fallback_used=fallback_used,
            final_reason=final_reason,
        )
        # A-side hard guard: if gate blockers exist, scorecard must not present a high score.
        # This prevents blocker paths from being masked by non-gate scoring dimensions.
        a_score_cap_applied = bool(a_gate_blocker_codes and pre_cap_total_score > 54.0)
        total_score = min(pre_cap_total_score, 54.0) if a_gate_blocker_codes else pre_cap_total_score
        a_gate_signoff_ready = bool(
            (not a_gate_blocker_codes)
            and gate_safety_score >= 80.0
            and audit_completeness_score >= 80.0
        )
        b_scores = self._build_b_side_scores(
            trace_id=trace_id,
            event_hash=event_hash,
            final_action=final_action,
            final_reason=final_reason,
            sector_candidates=sector_candidates,
            ticker_candidates=ticker_candidates,
            theme_tags=theme_tags,
            sectors=sectors,
            sector_impacts=sector_impacts,
            stock_candidates=stock_candidates,
            mapping_source=mapping_source,
            needs_manual_review=needs_manual_review,
            tradeable=tradeable,
            opportunity_count=opportunity_count,
        )

        return {
            "logged_at": self._utc_now(),
            "trace_id": trace_id,
            "event_trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "event_id": event_id,
            "event_hash": event_hash,
            "final_action": final_action,
            "final_reason": final_reason,
            "semantic_event_type": semantic_event_type,
            "sector_candidates": sector_candidates,
            "ticker_candidates": ticker_candidates,
            "theme_tags": theme_tags,
            "tradeable": tradeable,
            "opportunity_count": opportunity_count,
            "sectors": sectors,
            "sector_impacts": sector_impacts,
            "stock_candidates": stock_candidates,
            "scores": {
                "gate_safety_score": round(gate_safety_score, 2),
                "output_quality_score": round(output_quality_score, 2),
                "provider_freshness_score": round(provider_freshness_score, 2),
                "audit_completeness_score": round(audit_completeness_score, 2),
                "pre_cap_total_score": pre_cap_total_score,
                "total_score": total_score,
                "grade": self._grade_from_score(total_score),
            },
            "owner_dimensions": {
                "A_gate_safety": round(gate_safety_score, 2),
                "A_audit_completeness": round(audit_completeness_score, 2),
                "B_output_quality": round(output_quality_score, 2),
                "C_provider_freshness": round(provider_freshness_score, 2),
                "C_audit_completeness": round(audit_completeness_score, 2),
            },
            "a_gate_blocker_codes": a_gate_blocker_codes,
            "a_gate_blocker_count": len(a_gate_blocker_codes),
            "a_gate_blocker_present": bool(a_gate_blocker_codes),
            "a_score_cap_applied": a_score_cap_applied,
            "a_gate_signoff_ready": a_gate_signoff_ready,
            "mapping_source": b_scores["mapping_source"],
            "needs_manual_review": b_scores["needs_manual_review"],
            "placeholder_count": b_scores["placeholder_count"],
            "non_whitelist_sector_count": b_scores["non_whitelist_sector_count"],
            "ticker_truth_source_hit": b_scores["ticker_truth_source_hit"],
            "ticker_truth_source_miss": b_scores["ticker_truth_source_miss"],
            "sector_quality_score": b_scores["sector_quality_score"],
            "ticker_quality_score": b_scores["ticker_quality_score"],
            "output_quality_score": b_scores["output_quality_score"],
            "mapping_acceptance_score": b_scores["mapping_acceptance_score"],
            "b_overall_score": b_scores["b_overall_score"],
            "b_signoff_ready": b_scores["b_signoff_ready"],
            "b_quality_details": {
                "placeholder_total": b_scores["placeholder_total"],
                "placeholder_leakage_rate": b_scores["placeholder_leakage_rate"],
            },
        }

    def _refresh_stage5_daily_outputs(self) -> None:
        """Auto-refresh Stage5 daily artifacts after each run."""
        try:
            from system_log_evaluator import evaluate_logs

            evaluated = evaluate_logs(logs_dir=self.logs_dir, gate_enabled=True)
            (self.logs_dir / "provider_health_hourly.json").write_text(
                json.dumps(evaluated["provider_health_hourly"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (self.logs_dir / "system_health_daily.json").write_text(
                json.dumps(evaluated["system_health_daily"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (self.logs_dir / "system_health_daily_report.md").write_text(
                str(evaluated["daily_report_markdown"]),
                encoding="utf-8",
            )
        except Exception:
            # Keep trading pipeline non-blocking if observability artifact refresh fails.
            return

    @staticmethod
    def _event_hash(headline: str, ts: str) -> str:
        raw = f"{headline}|{ts}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16].upper()

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_market_validation_input(self, payload: Dict[str, Any], event_object: Dict[str, Any], conduction_out: Dict[str, Any]) -> Dict[str, Any]:
        raw_price = payload.get("price_changes")
        raw_volume = payload.get("volume_changes")

        price_changes = dict(raw_price) if isinstance(raw_price, dict) else {}
        volume_changes = dict(raw_volume) if isinstance(raw_volume, dict) else {}

        derived_from_payload = False
        if not price_changes:
            spx_move = self._to_float(payload.get("spx_move_pct"))
            vix_move = self._to_float(payload.get("vix_change_pct"))
            sector_move = self._to_float(payload.get("sector_move_pct"))
            if spx_move is not None:
                price_changes["SPY"] = spx_move
            if vix_move is not None:
                price_changes["VIX_PROXY"] = vix_move
            if sector_move is not None:
                price_changes["SECTOR_PROXY"] = sector_move
            derived_from_payload = bool(price_changes)

        if not volume_changes:
            spx_vol = self._to_float(payload.get("spx_volume_ratio"))
            sector_vol = self._to_float(payload.get("sector_volume_ratio"))
            if spx_vol is not None:
                volume_changes["SPY"] = spx_vol
            if sector_vol is not None:
                volume_changes["SECTOR_PROXY"] = sector_vol

        market_data_source = str(payload.get("market_data_source", "")).strip().lower()
        if not market_data_source:
            if isinstance(raw_price, dict) or isinstance(raw_volume, dict):
                market_data_source = "payload_direct"
            elif derived_from_payload:
                market_data_source = "payload_derived"
            else:
                market_data_source = "missing"

        market_data_stale = bool(payload.get("market_data_stale", False))
        market_data_default_used = bool(payload.get("market_data_default_used", False))
        market_data_fallback_used = bool(payload.get("market_data_fallback_used", False))

        if market_data_source in {"default", "synthetic_default"}:
            market_data_default_used = True
        if market_data_source in {"fallback", "failed"}:
            market_data_fallback_used = True

        market_data_present = bool(price_changes or volume_changes)
        if market_data_source in {"missing", "failed"} and not market_data_present:
            market_data_present = False

        cross_asset_linkage = payload.get("cross_asset_linkage")
        if not isinstance(cross_asset_linkage, dict):
            cross_asset_linkage = {"confirmed": False}
        else:
            cross_asset_linkage = {"confirmed": bool(cross_asset_linkage.get("confirmed", False))}

        winner_loser_dispersion = payload.get("winner_loser_dispersion")
        if not isinstance(winner_loser_dispersion, dict):
            winner_loser_dispersion = {"confirmed": False}
        else:
            winner_loser_dispersion = {"confirmed": bool(winner_loser_dispersion.get("confirmed", False))}

        persistence_minutes = self._to_float(payload.get("persistence_minutes"))
        if persistence_minutes is None:
            persistence_minutes = 0.0

        return {
            "event_id": event_object["event_id"],
            "conduction_output": {"conduction_path": conduction_out.get("conduction_path", [])},
            "price_changes": price_changes,
            "volume_changes": volume_changes,
            "cross_asset_linkage": cross_asset_linkage,
            "persistence_minutes": persistence_minutes,
            "winner_loser_dispersion": winner_loser_dispersion,
            "market_timestamp": payload.get("market_timestamp", event_object["updated_at"]),
            "market_data_source": market_data_source,
            "market_data_present": market_data_present,
            "market_data_stale": market_data_stale,
            "market_data_default_used": market_data_default_used,
            "market_data_fallback_used": market_data_fallback_used,
        }

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        intel_out = self.intel.run(payload)

        event_object = intel_out["event_object"]
        source_rank = intel_out["source_rank"]
        event_id = event_object["event_id"]
        request_id = payload.get("request_id")
        batch_id = payload.get("batch_id")
        trace_id = str(payload.get("trace_id") or event_id)
        event_hash = self._event_hash(event_object.get("headline", ""), str(event_object.get("detected_at", "")))

        self._append_jsonl(
            self.raw_news_ingest_log_path,
            {
                "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "trace_id": trace_id,
                "event_trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "event_id": event_id,
                "event_hash": event_hash,
                "headline": event_object.get("headline"),
                "source": payload.get("source"),
                "detected_at": event_object.get("detected_at"),
                "ingest_seq": payload.get("ingest_seq", payload.get("sequence")),
                "process_seq": payload.get("process_seq", payload.get("sequence")),
                "source_rank": source_rank,
            },
        )
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=1,
            stage="intel_ingest",
            status="success",
            details={"source_rank": source_rank.get("rank"), "headline": event_object.get("headline")},
        )

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
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=2,
            stage="lifecycle",
            status="success",
            details={"lifecycle_state": lifecycle_out.get("lifecycle_state"), "internal_state": lifecycle_out.get("internal_state")},
        )

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
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=3,
            stage="fatigue",
            status="success",
            details={"fatigue_final": fatigue_out.get("fatigue_final"), "watch_mode": fatigue_out.get("watch_mode")},
        )

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
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=4,
            stage="conduction",
            status="success",
            details={"confidence": conduction_out.get("confidence"), "path_len": len(conduction_out.get("conduction_path", []))},
        )

        validation_input = self._build_market_validation_input(payload, event_object, conduction_out)
        validation_out = self.validation.run(validation_input).data
        self._append_jsonl(
            self.market_data_provenance_log_path,
            {
                "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "trace_id": trace_id,
                "event_trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "event_id": event_id,
                "event_hash": event_hash,
                "market_data_source": validation_out.get("market_data_source", "unknown"),
                "market_data_present": bool(validation_out.get("market_data_present", False)),
                "market_data_stale": bool(validation_out.get("market_data_stale", False)),
                "market_data_default_used": bool(validation_out.get("market_data_default_used", False)),
                "market_data_fallback_used": bool(validation_out.get("market_data_fallback_used", False)),
                "validation_state": validation_out.get("validation_state"),
            },
        )
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=5,
            stage="market_validation",
            status="success",
            details={
                "market_data_source": validation_out.get("market_data_source"),
                "market_data_stale": bool(validation_out.get("market_data_stale", False)),
                "market_data_default_used": bool(validation_out.get("market_data_default_used", False)),
                "market_data_fallback_used": bool(validation_out.get("market_data_fallback_used", False)),
            },
        )

        semantic_out = self.semantic.analyze(event_object["headline"], payload.get("summary", event_object["headline"]))
        event_contract = self.semantic.analyze_event(
            event_object["headline"],
            payload.get("summary", event_object["headline"]),
            semantic_output=semantic_out,
            event_id=event_object["event_id"],
            event_time=event_object.get("detected_at", event_object.get("updated_at", "")),
        )
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=6,
            stage="semantic",
            status="success",
            details={"semantic_event_type": semantic_out.get("event_type", "other")},
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
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=7,
            stage="path_adjudication",
            status="success",
            details={"primary_path": (path_out.get("primary_path") or {}).get("path_text", "undetermined")},
        )

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
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=8,
            stage="signal",
            status="success",
            details={"score": signal_out.get("score"), "score_decision": signal_out.get("score_decision")},
        )

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
        opportunities = opportunity_update.get("opportunities", []) if isinstance(opportunity_update, dict) else []
        has_opportunity = bool(opportunities)
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=9,
            stage="opportunity",
            status="success",
            details={"opportunity_count": len(opportunities), "has_opportunity": has_opportunity},
        )

        contract_version = "v2.2"
        legacy_contract_version = "v1.0"
        analysis_out["contract_meta"] = {
            "contract_version": contract_version,
            "legacy_contract_version": legacy_contract_version,
            "dual_write": True,
        }

        execution_in = {
            "trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "event_hash": event_hash,
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
            "has_opportunity": has_opportunity,
            "opportunity_count": len(opportunities),
            "semantic_event_type": semantic_out.get("event_type", "other"),
            "sector_candidates": [item.get("sector") for item in conduction_out.get("sector_impacts", []) if item.get("sector")],
            "ticker_candidates": [item.get("symbol") for item in conduction_out.get("stock_candidates", []) if item.get("symbol")],
            "a1_score": validation_out.get("A1", 0),
            "theme_tags": payload.get("theme_tags", payload.get("narrative_tags", [])),
            "market_data_source": validation_out.get("market_data_source", "unknown"),
            "market_data_present": bool(validation_out.get("market_data_present", False)),
            "market_data_stale": bool(validation_out.get("market_data_stale", False)),
            "market_data_default_used": bool(validation_out.get("market_data_default_used", False)),
            "market_data_fallback_used": bool(validation_out.get("market_data_fallback_used", False)),
            "enforce_resolved_symbol": True,
            "tradeable": has_opportunity and validation_out.get("a1_market_validation") != "fail",
            "contract_version": contract_version,
            "legacy_contract_version": legacy_contract_version,
            "dual_write": True,
        }
        execution_out = self.execution.run(execution_in)
        final = execution_out.get("final", {}) if isinstance(execution_out, dict) else {}
        final_action = str(final.get("action", "UNKNOWN")).upper()
        final_reason = str(final.get("reason", ""))
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=10,
            stage="execution",
            status="success",
            details={"final_action": final_action, "final_reason": final_reason},
        )

        if final_action in {"WATCH", "BLOCK", "FORCE_CLOSE", "PENDING_CONFIRM"}:
            reject_reason_code = "EXECUTION_GATE_REJECTED"
            if "missing_opportunity" in final_reason:
                reject_reason_code = "MISSING_OPPORTUNITY"
            elif "market_data_default_used" in final_reason:
                reject_reason_code = "MARKET_DATA_DEFAULT_USED"
            elif "market_data_fallback_used" in final_reason:
                reject_reason_code = "MARKET_DATA_FALLBACK_USED"
            elif "market_data_stale" in final_reason:
                reject_reason_code = "MARKET_DATA_STALE"

            rejected_record = {
                "logged_at": self._utc_now(),
                "trace_id": trace_id,
                "event_trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "event_id": event_id,
                "event_hash": event_hash,
                "stage": "execution",
                "reject_reason_code": reject_reason_code,
                "reject_reason_text": final_reason,
                "contract_version": execution_in.get("contract_version", "v2.2"),
                "ingest_ts": event_object.get("detected_at"),
                "decision_ts": self._utc_now(),
                "final_action": final_action,
            }
            self._append_jsonl(self.rejected_events_log_path, rejected_record)

            quarantine_record = {
                "logged_at": self._utc_now(),
                "trace_id": trace_id,
                "event_trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "event_id": event_id,
                "event_hash": event_hash,
                "stage": "execution",
                "reject_reason_code": reject_reason_code,
                "reject_reason_text": final_reason,
                "ingest_ts": event_object.get("detected_at"),
                "decision_ts": self._utc_now(),
                "final_action": final_action,
                "contract_version": execution_in.get("contract_version", "v2.2"),
            }
            self._append_jsonl(self.quarantine_replay_log_path, quarantine_record)

        trace_scorecard = self._build_trace_scorecard(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            execution_in=execution_in,
            execution_out=execution_out,
            conduction_out=conduction_out,
            sectors=sectors,
        )
        self._append_jsonl(self.trace_scorecard_log_path, trace_scorecard)

        self.state_store.upsert_state(event_id, {
            "internal_state": lifecycle_out["internal_state"],
            "lifecycle_state": lifecycle_out["lifecycle_state"],
            "catalyst_state": lifecycle_out["catalyst_state"],
            "retry_count": retry_count + 1,
            "metadata": {
                "category": event_object["category"],
            },
        })
        self._refresh_stage5_daily_outputs()

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
