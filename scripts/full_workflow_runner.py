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
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conduction_mapper import ConductionMapper
from fatigue_calculator import FatigueCalculator
from ai_semantic_analyzer import SemanticAnalyzer
from intel_modules import IntelPipeline
from lifecycle_manager import LifecycleManager
from market_validator import MarketValidator
from opportunity_score import OpportunityScorer
from execution_suggestion_builder import ExecutionSuggestionBuilder
from signal_scorer import SignalScorer
from state_store import EventStateStore
from workflow_runner import WorkflowRunner
from transmission_engine.core.path_adjudicator import PathAdjudicator
from edt_module_base import ModuleStatus


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
        self.execution_suggestion_builder = ExecutionSuggestionBuilder()
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

    @staticmethod
    def _norm_text(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _contains_placeholder_like(value: Any) -> bool:
        txt = FullWorkflowRunner._norm_text(value)
        return any(token in txt for token in ("placeholder", "template collapse", "template", "unknown_placeholder"))

    @staticmethod
    def _is_missing_provenance_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        return False

    def _load_sector_whitelist(self) -> set[str]:
        cfg_path = ROOT / "configs" / "sector_impact_mapping.yaml"
        if not cfg_path.exists():
            return set()
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        out: set[str] = set()
        mappings = cfg.get("mappings", [])
        if isinstance(mappings, list):
            for row in mappings:
                if isinstance(row, dict) and row.get("sector"):
                    out.add(str(row["sector"]).strip())
        mapping = cfg.get("mapping", {})
        if isinstance(mapping, dict):
            for values in mapping.values():
                if isinstance(values, list):
                    for name in values:
                        if str(name).strip():
                            out.add(str(name).strip())
        return out

    def _load_ticker_truth_pool(self) -> set[str]:
        cfg_path = ROOT / "configs" / "premium_stock_pool.yaml"
        if not cfg_path.exists():
            return set()
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        out: set[str] = set()
        for row in cfg.get("stocks", []):
            if isinstance(row, dict) and row.get("symbol"):
                out.add(str(row["symbol"]).strip().upper())
        return out

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
        conduction_out: Dict[str, Any] | None = None,
        sectors: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        final = execution_out.get("final", {}) if isinstance(execution_out, dict) else {}
        final_action = str(final.get("action", "UNKNOWN")).upper()
        stale = bool(execution_in.get("market_data_stale", False))
        default_used = bool(execution_in.get("market_data_default_used", False))
        fallback_used = bool(execution_in.get("market_data_fallback_used", False))
        has_opportunity = bool(execution_in.get("has_opportunity", False))
        semantic_event_type = str(execution_in.get("semantic_event_type", "unknown"))
        sector_candidates = execution_in.get("sector_candidates", [])
        ticker_candidates = execution_in.get("ticker_candidates", [])
        conduction_data = conduction_out if isinstance(conduction_out, dict) else {}
        sector_impacts = conduction_data.get("sector_impacts")
        if not isinstance(sector_impacts, list):
            sector_impacts = execution_in.get("sector_impacts", [])
        stock_candidates = conduction_data.get("stock_candidates")
        if not isinstance(stock_candidates, list):
            stock_candidates = execution_in.get("stock_candidates", [])
        mapping_source = str(
            conduction_data.get("mapping_source", execution_in.get("mapping_source", "unknown"))
        ).strip()
        needs_manual_review = bool(
            conduction_data.get("needs_manual_review", execution_in.get("needs_manual_review", False))
        )
        tradeable = execution_in.get("tradeable")
        opportunity_count = execution_in.get("opportunity_count")
        final_reason = str(final.get("reason", ""))
        theme_tags = execution_in.get("theme_tags", [])
        def _safe_int(value: Any, default: int = 0) -> int:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return default

        ai_sentiment = str(execution_in.get("sentiment", "neutral") or "neutral")
        ai_confidence = _safe_int(execution_in.get("confidence", 0), 0)
        ai_recommended_chain = str(execution_in.get("recommended_chain", "") or "")
        ai_recommended_stocks_raw = execution_in.get("recommended_stocks", [])
        ai_a0_event_strength = _safe_int(execution_in.get("a0_event_strength", 0), 0)
        ai_expectation_gap = _safe_int(execution_in.get("expectation_gap", 0), 0)
        ai_transmission_candidates_raw = execution_in.get("transmission_candidates", [])
        semantic_fallback_reason = str(execution_in.get("semantic_fallback_reason", "") or "")

        ai_recommended_stocks = (
            [str(x).strip() for x in ai_recommended_stocks_raw if str(x).strip()]
            if isinstance(ai_recommended_stocks_raw, list)
            else []
        )
        ai_transmission_candidates = (
            [str(x).strip() for x in ai_transmission_candidates_raw if str(x).strip()]
            if isinstance(ai_transmission_candidates_raw, list)
            else []
        )
        semantic_missing_fields = execution_in.get("semantic_missing_fields", [])
        if not isinstance(semantic_missing_fields, list):
            semantic_missing_fields = []
        ai_missing_fields = [str(x) for x in semantic_missing_fields if str(x).strip()]
        semantic_defaults_applied = bool(execution_in.get("semantic_defaults_applied", False))

        sector_whitelist = self._load_sector_whitelist()
        ticker_truth_pool = self._load_ticker_truth_pool()

        sectors_payload = sectors if isinstance(sectors, list) else execution_in.get("sectors", [])
        sectors_list: List[str] = []
        if isinstance(sectors_payload, list):
            for row in sectors_payload:
                if isinstance(row, dict):
                    name = str(row.get("name", "")).strip()
                else:
                    name = str(row).strip()
                if name:
                    sectors_list.append(name)
        non_whitelist_sector_count = sum(
            1
            for name in sectors_list
            if str(name).strip() and (str(name).strip() not in sector_whitelist)
        )

        ticker_candidates_list = [str(t).strip().upper() for t in ticker_candidates if str(t).strip()]
        ticker_truth_source_hit = sum(1 for t in ticker_candidates_list if t in ticker_truth_pool)
        ticker_truth_source_miss = sum(1 for t in ticker_candidates_list if t not in ticker_truth_pool)

        placeholder_count = 0
        for raw in sectors_list + ticker_candidates_list + list(theme_tags if isinstance(theme_tags, list) else []):
            if self._contains_placeholder_like(raw):
                placeholder_count += 1

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
        if placeholder_count > 0:
            output_quality_score -= 40.0
        if needs_manual_review:
            output_quality_score -= 15.0
        if not final_reason:
            output_quality_score -= 15.0
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

        sector_quality_score = 100.0
        if not sectors_list:
            sector_quality_score -= 100.0
        if non_whitelist_sector_count > 0:
            sector_quality_score -= 100.0
        if not sector_impacts:
            sector_quality_score -= 20.0
        if not mapping_source:
            sector_quality_score -= 20.0
        sector_quality_score = max(0.0, min(100.0, sector_quality_score))

        ticker_quality_score = 100.0
        if not ticker_candidates_list:
            ticker_quality_score -= 100.0
        if ticker_truth_source_miss > 0:
            ticker_quality_score -= 100.0
        if ticker_truth_source_hit == 0:
            ticker_quality_score -= 40.0
        if not stock_candidates:
            ticker_quality_score -= 20.0
        ticker_quality_score = max(0.0, min(100.0, ticker_quality_score))

        mapping_acceptance_score = 100.0
        if not trace_id:
            mapping_acceptance_score -= 40.0
        if not event_hash:
            mapping_acceptance_score -= 40.0
        if not semantic_event_type or semantic_event_type == "unknown":
            mapping_acceptance_score -= 20.0
        if not sector_candidates:
            mapping_acceptance_score -= 20.0
        if not ticker_candidates:
            mapping_acceptance_score -= 20.0
        if not final_action:
            mapping_acceptance_score -= 20.0
        if not final_reason:
            mapping_acceptance_score -= 20.0
        mapping_acceptance_score = max(0.0, min(100.0, mapping_acceptance_score))

        b_overall_score = min(sector_quality_score, ticker_quality_score, output_quality_score, mapping_acceptance_score)
        b_signoff_ready = bool(
            non_whitelist_sector_count == 0
            and ticker_truth_source_miss == 0
            and placeholder_count == 0
            and sector_quality_score >= 80.0
            and ticker_quality_score >= 80.0
            and output_quality_score >= 80.0
            and mapping_acceptance_score >= 80.0
            and b_overall_score >= 80.0
        )

        a_gate_blocker_codes: List[str] = []
        reason_lower = final_reason.lower()
        if (not has_opportunity) or ("missing_opportunity" in reason_lower):
            a_gate_blocker_codes.append("MISSING_OPPORTUNITY")
        if stale or ("market_data_stale" in reason_lower):
            a_gate_blocker_codes.append("MARKET_DATA_STALE")
        if default_used or ("market_data_default_used" in reason_lower):
            a_gate_blocker_codes.append("MARKET_DATA_DEFAULT_USED")
        if fallback_used or ("market_data_fallback_used" in reason_lower):
            a_gate_blocker_codes.append("MARKET_DATA_FALLBACK_USED")
        a_gate_blocker_codes = sorted(set(a_gate_blocker_codes))
        a_gate_blocker_count = len(a_gate_blocker_codes)
        a_gate_blocker_present = a_gate_blocker_count > 0
        pre_cap_total_score = (
            0.35 * gate_safety_score
            + 0.30 * output_quality_score
            + 0.20 * provider_freshness_score
            + 0.15 * audit_completeness_score
        )
        pre_cap_total_score = round(max(0.0, min(100.0, pre_cap_total_score)), 2)
        a_score_cap_applied = bool(a_gate_blocker_present and pre_cap_total_score > 54.0)
        a_gate_signoff_ready = bool(
            (not a_gate_blocker_present)
            and gate_safety_score >= 80.0
            and audit_completeness_score >= 80.0
        )

        total_score = min(pre_cap_total_score, 54.0) if a_gate_blocker_present else pre_cap_total_score

        return {
            "logged_at": self._utc_now(),
            "trace_id": trace_id,
            "event_trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "event_id": event_id,
            "event_hash": event_hash,
            "semantic_event_type": semantic_event_type,
            "sector_candidates": list(sector_candidates) if isinstance(sector_candidates, list) else [],
            "ticker_candidates": list(ticker_candidates) if isinstance(ticker_candidates, list) else [],
            "theme_tags": list(theme_tags) if isinstance(theme_tags, list) else [],
            "tradeable": tradeable,
            "opportunity_count": opportunity_count,
            "decision_price": execution_in.get("decision_price"),
            "decision_price_source": str(execution_in.get("decision_price_source") or "missing"),
            "needs_price_refresh": execution_in.get("needs_price_refresh"),
            "decision_prices_by_symbol": execution_in.get("decision_prices_by_symbol", {}),
            "final_action": final_action,
            "final_reason": final_reason,
            "sectors[]": sectors_list,
            "sector_impacts": list(sector_impacts) if isinstance(sector_impacts, list) else [],
            "stock_candidates": list(stock_candidates) if isinstance(stock_candidates, list) else [],
            "mapping_source": mapping_source,
            "needs_manual_review": needs_manual_review,
            "placeholder_count": placeholder_count,
            "non_whitelist_sector_count": non_whitelist_sector_count,
            "ticker_truth_source_hit": ticker_truth_source_hit,
            "ticker_truth_source_miss": ticker_truth_source_miss,
            "sector_quality_score": round(sector_quality_score, 2),
            "ticker_quality_score": round(ticker_quality_score, 2),
            "output_quality_score": round(output_quality_score, 2),
            "mapping_acceptance_score": round(mapping_acceptance_score, 2),
            "b_overall_score": round(b_overall_score, 2),
            "b_signoff_ready": b_signoff_ready,
            "ai_sentiment": ai_sentiment,
            "ai_confidence": ai_confidence,
            "ai_recommended_chain": ai_recommended_chain,
            "ai_recommended_stocks": ai_recommended_stocks,
            "ai_a0_event_strength": ai_a0_event_strength,
            "ai_expectation_gap": ai_expectation_gap,
            "ai_transmission_candidates": ai_transmission_candidates,
            "semantic_fallback_reason": semantic_fallback_reason,
            "ai_missing_fields": ai_missing_fields,
            "semantic_defaults_applied": semantic_defaults_applied,
            "a_gate_blocker_codes": a_gate_blocker_codes,
            "a_gate_blocker_count": a_gate_blocker_count,
            "a_gate_blocker_present": a_gate_blocker_present,
            "a_score_cap_applied": a_score_cap_applied,
            "a_gate_signoff_ready": a_gate_signoff_ready,
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
                # Backward-compatible alias retained for existing Stage5 checks.
                "A_audit_completeness": round(audit_completeness_score, 2),
                "B_output_quality": round(output_quality_score, 2),
                "B_sector_quality": round(sector_quality_score, 2),
                "B_ticker_quality": round(ticker_quality_score, 2),
                "B_mapping_acceptance": round(mapping_acceptance_score, 2),
                "B_overall_score": round(b_overall_score, 2),
                "C_provider_freshness": round(provider_freshness_score, 2),
                "C_audit_completeness": round(audit_completeness_score, 2),
            },
        }

    def _refresh_stage5_daily_outputs(self) -> None:
        """Best-effort generation of Stage5 daily health artifacts."""
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
            # Do not block the main trading path on observability export errors.
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

    @staticmethod
    def _provider_meta_from_opportunity(scorer: OpportunityScorer) -> Dict[str, Any]:
        adapter = getattr(scorer, "_market_data_adapter", None)
        meta = getattr(adapter, "last_meta", None)
        if meta is None:
            return {
                "provider_chain": [],
                "providers_attempted": [],
                "providers_succeeded": [],
                "providers_failed": [],
                "provider_failure_reasons": {},
                "fallback_used": False,
                "fallback_reason": "",
                "unresolved_symbols": [],
            }
        return {
            "provider_chain": list(getattr(meta, "provider_chain", []) or []),
            "providers_attempted": list(getattr(meta, "attempted", []) or []),
            "providers_succeeded": list(getattr(meta, "succeeded", []) or []),
            "providers_failed": list(getattr(meta, "failed", []) or []),
            "provider_failure_reasons": dict(getattr(meta, "failure_reasons", {}) or {}),
            "fallback_used": bool(getattr(meta, "fallback_used", False)),
            "fallback_reason": str(getattr(meta, "fallback_reason", "") or ""),
            "unresolved_symbols": list(getattr(meta, "unresolved_symbols", []) or []),
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
        derived_symbols_requested = sorted(
            {
                str(sym).strip().upper()
                for sym in list((validation_input.get("price_changes") or {}).keys())
                + list((validation_input.get("volume_changes") or {}).keys())
                if str(sym).strip()
            }
        )
        derived_symbols_returned = sorted(
            {
                str(sym).strip().upper()
                for source in ((validation_input.get("price_changes") or {}), (validation_input.get("volume_changes") or {}))
                for sym, value in source.items()
                if str(sym).strip() and value is not None
            }
        )
        def _normalize_symbols(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, str):
                raw_items = [value]
            elif isinstance(value, (list, tuple, set)):
                raw_items = list(value)
            else:
                raw_items = [value]
            return sorted({str(sym).strip().upper() for sym in raw_items if str(sym).strip()})

        payload_symbols_requested = _normalize_symbols(payload.get("symbols_requested")) if "symbols_requested" in payload else None
        payload_symbols_returned = _normalize_symbols(payload.get("symbols_returned")) if "symbols_returned" in payload else None
        symbols_requested = payload_symbols_requested if payload_symbols_requested is not None else derived_symbols_requested
        symbols_returned = payload_symbols_returned if payload_symbols_returned is not None else derived_symbols_returned
        provenance_record = {
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
            "market_data_provider": payload.get("market_data_provider"),
            "provider_path": payload.get("provider_path"),
            "symbols_requested": symbols_requested,
            "symbols_returned": symbols_returned,
            "request_mode": payload.get("request_mode"),
            "fetch_latency_ms": payload.get("fetch_latency_ms"),
            "market_data_ts": payload.get("market_timestamp"),
            "market_data_delay_seconds": payload.get("market_data_delay_seconds"),
            "rate_limited": payload.get("rate_limited"),
            "http_status": payload.get("http_status"),
            "error_code": payload.get("error_code"),
            "used_by_module": "MarketValidator",
            "provenance_field_missing": [],
        }
        missing_fields = []
        for field in (
            "market_data_provider",
            "provider_path",
            "request_mode",
            "fetch_latency_ms",
            "market_data_ts",
            "market_data_delay_seconds",
            "rate_limited",
            "http_status",
            "error_code",
        ):
            if self._is_missing_provenance_value(provenance_record.get(field)):
                missing_fields.append(field)
        if not symbols_requested:
            missing_fields.append("symbols_requested")
        if not symbols_returned:
            missing_fields.append("symbols_returned")
        provenance_record["provenance_field_missing"] = missing_fields
        self._append_jsonl(
            self.market_data_provenance_log_path,
            provenance_record,
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
        semantic_required_fields = (
            "sentiment",
            "confidence",
            "recommended_chain",
            "recommended_stocks",
            "a0_event_strength",
            "expectation_gap",
            "transmission_candidates",
        )
        semantic_missing_fields = [key for key in semantic_required_fields if key not in semantic_out]
        semantic_defaults_applied = bool(semantic_missing_fields)
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
            "lifecycle_fatigue_contract": {
                "schema_version": "stage6.lifecycle_fatigue.v1",
                "lifecycle_state": lifecycle_out.get("lifecycle_state"),
                "time_scale": lifecycle_out.get("time_scale"),
                "decay_profile": lifecycle_out.get("decay_profile"),
                "fatigue_score": fatigue_out.get("fatigue_score", fatigue_out.get("fatigue_final")),
                "fatigue_bucket": fatigue_out.get("fatigue_bucket"),
                "stale_event": lifecycle_out.get("stale_event"),
            },
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
        selected_opp = None
        for opp in opportunities:
            if opp.get("decision_price") is not None:
                selected_opp = opp
                break
        if selected_opp is None and opportunities:
            selected_opp = opportunities[0]
        primary_decision_price = selected_opp.get("decision_price") if selected_opp else None

        execution_suggestion_in = {
            "score": signal_out.get("score"),
            "fatigue_score": fatigue_out.get("fatigue_score"),
            "has_opportunity": has_opportunity,
            "market_validated": validation_out.get("a1_market_validation") == "pass",
            "lifecycle_state": lifecycle_out.get("lifecycle_state", "Detected"),
            "stale_event": lifecycle_out.get("stale_event", {}),
        }
        execution_suggestion_out = self.execution_suggestion_builder.run(execution_suggestion_in)
        if execution_suggestion_out.status == ModuleStatus.SUCCESS:
            analysis_out["execution_suggestion"] = execution_suggestion_out.data
        else:
            analysis_out["execution_suggestion_status"] = "failed"
            analysis_out["execution_suggestion_errors"] = execution_suggestion_out.errors
            self._log_pipeline_stage(
                trace_id=trace_id,
                event_id=event_id,
                request_id=request_id,
                batch_id=batch_id,
                event_hash=event_hash,
                stage_seq=10,
                stage="execution_suggestion",
                status="failed",
                details={"errors": execution_suggestion_out.errors},
            )

        # Build per-symbol price map for multi-opportunity scenarios
        decision_prices_by_symbol: Dict[str, Dict[str, Any]] = {}
        for opp in opportunities:
            sym_raw = opp.get("symbol") or opp.get("ticker")
            sym = str(sym_raw).strip().upper() if sym_raw else ""
            if not sym:
                continue
            decision_price = opp.get("decision_price")
            decision_price_source = opp.get("decision_price_source")
            if decision_price is None and not str(decision_price_source or "").strip():
                decision_price_source = "missing"
            needs_price_refresh = opp.get("needs_price_refresh")
            if needs_price_refresh is None:
                needs_price_refresh = decision_price is None
            decision_prices_by_symbol[sym] = {
                "decision_price": decision_price,
                "decision_price_source": decision_price_source,
                "needs_price_refresh": needs_price_refresh,
                "final_action": opp.get("final_action"),
            }
        provider_meta = {}
        if isinstance(opportunity_update, dict):
            raw_provider_meta = opportunity_update.get("provider_meta")
            if isinstance(raw_provider_meta, dict):
                provider_meta = {
                    "provider_chain": list(raw_provider_meta.get("provider_chain", []) or []),
                    "providers_attempted": list(raw_provider_meta.get("providers_attempted", []) or []),
                    "providers_succeeded": list(raw_provider_meta.get("providers_succeeded", []) or []),
                    "providers_failed": list(raw_provider_meta.get("providers_failed", []) or []),
                    "provider_failure_reasons": dict(raw_provider_meta.get("provider_failure_reasons", {}) or {}),
                    "fallback_used": bool(raw_provider_meta.get("fallback_used", False)),
                    "fallback_reason": str(raw_provider_meta.get("fallback_reason", "") or ""),
                    "unresolved_symbols": list(raw_provider_meta.get("unresolved_symbols", []) or []),
                }
        if not provider_meta:
            provider_meta = self._provider_meta_from_opportunity(self.opportunity)
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
                "provider_chain": provider_meta["provider_chain"],
                "providers_attempted": provider_meta["providers_attempted"],
                "providers_succeeded": provider_meta["providers_succeeded"],
                "providers_failed": provider_meta["providers_failed"],
                "provider_failure_reasons": provider_meta["provider_failure_reasons"],
                "fallback_used": provider_meta["fallback_used"],
                "fallback_reason": provider_meta["fallback_reason"],
                "unresolved_symbols": provider_meta["unresolved_symbols"],
                "unresolved_symbol_count": len(provider_meta["unresolved_symbols"]),
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
            "sentiment": semantic_out.get("sentiment", "neutral"),
            "confidence": semantic_out.get("confidence", 0),
            "recommended_chain": semantic_out.get("recommended_chain", ""),
            "recommended_stocks": semantic_out.get("recommended_stocks", []),
            "a0_event_strength": semantic_out.get("a0_event_strength", 0),
            "expectation_gap": semantic_out.get("expectation_gap", 0),
            "transmission_candidates": semantic_out.get("transmission_candidates", []),
            "semantic_fallback_reason": semantic_out.get("fallback_reason", ""),
            "semantic_missing_fields": semantic_missing_fields,
            "semantic_defaults_applied": semantic_defaults_applied,
            "semantic_event_type": semantic_out.get("event_type", "other"),
            "sector_candidates": [item.get("sector") for item in conduction_out.get("sector_impacts", []) if item.get("sector")],
            "ticker_candidates": [item.get("symbol") for item in conduction_out.get("stock_candidates", []) if item.get("symbol")],
            "sectors": [item.get("sector") for item in conduction_out.get("sector_impacts", []) if item.get("sector")],
            "sector_impacts": conduction_out.get("sector_impacts", []),
            "stock_candidates": conduction_out.get("stock_candidates", []),
            "mapping_source": conduction_out.get("mapping_source", ""),
            "needs_manual_review": bool(conduction_out.get("needs_manual_review", False)),
            "a1_score": validation_out.get("A1", 0),
            "theme_tags": payload.get("theme_tags", payload.get("narrative_tags", [])),
            "market_data_source": validation_out.get("market_data_source", "unknown"),
            "market_data_present": bool(validation_out.get("market_data_present", False)),
            "market_data_stale": bool(validation_out.get("market_data_stale", False)),
            "market_data_default_used": bool(validation_out.get("market_data_default_used", False)),
            "market_data_fallback_used": bool(validation_out.get("market_data_fallback_used", False)),
            "enforce_resolved_symbol": True,
            "tradeable": has_opportunity and validation_out.get("a1_market_validation") != "fail",
            "decision_price": primary_decision_price,
            "decision_price_source": selected_opp.get("decision_price_source") if selected_opp else None,
            "needs_price_refresh": selected_opp.get("needs_price_refresh") if selected_opp else None,
            "decision_prices_by_symbol": decision_prices_by_symbol,
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
