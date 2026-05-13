#!/usr/bin/env python3
"""
Full-chain runner: Intel -> Analysis -> Execution.
"""

from __future__ import annotations

import hashlib
import json
import threading
from copy import deepcopy
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
from path_quality_evaluator import PathQualityEvaluator
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
        self.path_quality_evaluator = PathQualityEvaluator()
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

    def _upsert_jsonl_record(self, path: Path, record: Dict[str, Any], key_fields: tuple[str, ...]) -> None:
        """Append or merge a JSONL record by stable key fields."""
        with self._evidence_lock:
            rows: list[dict[str, Any]] = []
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        rows.append({"_raw": line})
            record_key = tuple(str(record.get(field, "")) for field in key_fields)
            replaced = False
            for idx, row in enumerate(rows):
                row_key = tuple(str(row.get(field, "")) for field in key_fields)
                if row_key == record_key:
                    merged = dict(row)
                    merged.update(record)
                    rows[idx] = merged
                    replaced = True
                    break
            if not replaced:
                rows.append(record)
            with open(path, "w", encoding="utf-8") as f:
                for row in rows:
                    if set(row.keys()) == {"_raw"}:
                        f.write(f"{row['_raw']}\n")
                    else:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
        return default

    def _load_feature_flags(self) -> Dict[str, bool]:
        """Load v2.2 feature flags from config single source.

        Missing/invalid config degrades safely to implementation defaults and
        never enables legacy replacement in Impl-1.
        """
        defaults = {
            "enable_v5_shadow_output": True,
            "enable_replace_legacy_output": False,
            "enable_conduction_split": True,
            "enable_semantic_prepass": True,
            "enable_source_metadata_propagation": False,
            "enable_candidate_envelope": False,
            "enable_entity_resolver": False,
            "enable_unified_candidate_pool": False,
            "enable_multisource_merge": False,
        }
        cfg_path = ROOT / "configs" / "feature_flags_v22.yaml"
        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            flags = raw.get("flags", {}) if isinstance(raw, dict) else {}
            if not isinstance(flags, dict):
                return dict(defaults)
            resolved: Dict[str, bool] = {}
            for key, dft in defaults.items():
                entry = flags.get(key, {})
                value = entry.get("default") if isinstance(entry, dict) else None
                resolved[key] = self._coerce_bool(value, dft)
            return resolved
        except (OSError, yaml.YAMLError):
            return dict(defaults)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _build_market_data_provenance_record(
        self,
        *,
        trace_id: str,
        request_id: str | None,
        batch_id: str | None,
        event_id: str,
        event_hash: str,
        validation_out: Dict[str, Any],
        payload: Dict[str, Any],
        derived_symbols_requested: list[str] | None = None,
        derived_symbols_returned: list[str] | None = None,
        provider_meta: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
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
        symbols_requested = payload_symbols_requested if payload_symbols_requested is not None else (derived_symbols_requested or [])
        symbols_returned = payload_symbols_returned if payload_symbols_returned is not None else (derived_symbols_returned or [])
        provider_meta = provider_meta or {}
        record = {
            "logged_at": self._utc_now(),
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
            "provider_chain": list(provider_meta.get("provider_chain", []) or []),
            "providers_attempted": list(provider_meta.get("providers_attempted", []) or []),
            "providers_succeeded": list(provider_meta.get("providers_succeeded", []) or []),
            "providers_failed": list(provider_meta.get("providers_failed", []) or []),
            "provider_failure_reasons": dict(provider_meta.get("provider_failure_reasons", {}) or {}),
            "fallback_used": bool(provider_meta.get("fallback_used", False)),
            "fallback_reason": str(provider_meta.get("fallback_reason", "") or ""),
            "unresolved_symbols": list(provider_meta.get("unresolved_symbols", []) or []),
            "unresolved_symbol_count": len(provider_meta.get("unresolved_symbols", []) or []),
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
            if self._is_missing_provenance_value(record.get(field)):
                missing_fields.append(field)
        if not symbols_requested:
            missing_fields.append("symbols_requested")
        if not symbols_returned:
            missing_fields.append("symbols_returned")
        record["provenance_field_missing"] = missing_fields
        return record

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

    @staticmethod
    def _build_semantic_prepass_contract(
        *,
        semantic_out: Dict[str, Any],
        headline: str,
    ) -> Dict[str, Any]:
        """Stage8A-Impl-1: lightweight semantic prepass contract."""
        event_type = str(semantic_out.get("event_type", "unknown") or "unknown")
        sentiment = str(semantic_out.get("sentiment", "neutral") or "neutral").lower()
        transmission_candidates = semantic_out.get("transmission_candidates", [])
        recommended_stocks = semantic_out.get("recommended_stocks", [])
        confidence_raw = semantic_out.get("confidence", 0)
        try:
            semantic_confidence = float(confidence_raw)
        except (TypeError, ValueError):
            semantic_confidence = 0.0

        if semantic_confidence > 1.0:
            semantic_confidence = semantic_confidence / 100.0
        semantic_confidence = max(0.0, min(1.0, semantic_confidence))

        if isinstance(transmission_candidates, list) and transmission_candidates:
            route_type = "company_anchor"
        elif event_type in {"policy", "macro", "rates"}:
            route_type = "macro_event"
        elif event_type in {"sector", "industry", "supply_chain"}:
            route_type = "sector_event"
        else:
            route_type = "unknown"

        if sentiment in {"positive", "bullish"}:
            event_direction = "positive"
        elif sentiment in {"negative", "bearish"}:
            event_direction = "negative"
        elif sentiment in {"mixed"}:
            event_direction = "mixed"
        else:
            event_direction = "neutral"

        anchor_entities: list[str] = []
        if isinstance(recommended_stocks, list):
            anchor_entities = [str(x).strip() for x in recommended_stocks if str(x).strip()]

        market_hint = "UNKNOWN"
        headline_u = str(headline or "").upper()
        if any(token in headline_u for token in ("NASDAQ", "NYSE", "S&P", "SPX", "DOW", "FED")):
            market_hint = "US"

        return {
            "route_type": route_type,
            "event_type": event_type,
            "event_direction": event_direction,
            "anchor_entities": anchor_entities,
            "semantic_confidence": semantic_confidence,
            "market_hint": market_hint,
            "needs_full_semantic": True,
            "prepass_latency_ms": 0,
        }

    @staticmethod
    def _candidate_role(candidate: Dict[str, Any]) -> str:
        source = str(candidate.get("source", "")).strip().lower()
        if source in {"semantic", "semantic_analyzer"}:
            return "semantic"
        if source in {"config"}:
            return "template"
        if source in {"tier1_ticker_pool"}:
            return "ticker_pool"
        if source in {"pool_fallback"}:
            return "fallback"
        if source:
            return source
        if str(candidate.get("sector_score_source", "")).strip():
            return str(candidate.get("sector_score_source"))
        return "unknown"

    @staticmethod
    def _candidate_relation(candidate: Dict[str, Any]) -> str:
        if bool(candidate.get("whether_direct_ticker_mentioned", False)):
            return "anchor"
        source = str(candidate.get("source", "")).strip().lower()
        if source in {"semantic", "semantic_analyzer"}:
            return "peer"
        if source in {"config"}:
            return "template"
        if source in {"tier1_ticker_pool"}:
            return "ticker_pool"
        if source in {"pool_fallback"}:
            return "fallback"
        return "derived"

    @staticmethod
    def _dedupe_ordered_symbols(symbols: List[str]) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized = str(symbol or "").strip().upper()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out

    @staticmethod
    def _dedupe_ordered_text(values: List[Any]) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out

    @staticmethod
    def _candidate_missing_provenance_reason(candidate: Dict[str, Any]) -> str | None:
        if not str(candidate.get("symbol", "")).strip():
            return "missing_symbol"
        if not str(candidate.get("source", "")).strip():
            return "missing_source"
        if not str(candidate.get("role", "")).strip():
            return "missing_role"
        if not str(candidate.get("relation", "")).strip():
            return "missing_relation"
        if not str(candidate.get("event_id", "")).strip():
            return "missing_event_id"
        return None

    def _propagate_candidate_metadata(
        self,
        candidate_generation_out: Dict[str, Any],
        *,
        trace_id: str,
        event_id: str,
        source_rank: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Attach source metadata to candidate generation output without changing legacy behavior."""
        out = deepcopy(candidate_generation_out)
        mapping_source = str(out.get("mapping_source") or "conduction_candidate_generation")
        source_rank_rank = str(source_rank.get("rank", "unknown") or "unknown")
        source_rank_confidence = source_rank.get("confidence")
        if source_rank_confidence is None:
            source_rank_confidence = source_rank.get("rank_confidence")
        for cand in out.get("stock_candidates", []):
            if not isinstance(cand, dict):
                continue
            cand.setdefault("event_id", event_id)
            cand.setdefault("trace_id", trace_id)
            cand.setdefault("candidate_origin", mapping_source)
            cand.setdefault("role", self._candidate_role(cand))
            cand.setdefault("relation", self._candidate_relation(cand))
            cand.setdefault("source_rank", source_rank_rank)
            if source_rank_confidence is not None:
                cand.setdefault("source_rank_confidence", source_rank_confidence)
            cand.setdefault("source_metadata_status", "propagated")
        out["candidate_origin"] = mapping_source
        out["event_id"] = event_id
        out["trace_id"] = trace_id
        out["source_rank"] = dict(source_rank)
        out["source_metadata_status"] = "propagated"
        return out

    def _build_candidate_envelope_surface(
        self,
        candidate_generation_out: Dict[str, Any],
        *,
        trace_id: str,
        event_id: str,
        source_rank: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a shadow-only CandidateEnvelope compatibility surface."""
        stock_candidates = candidate_generation_out.get("stock_candidates", [])
        mapping_source = str(candidate_generation_out.get("mapping_source") or "conduction_candidate_generation")
        source_rank_rank = str(source_rank.get("rank", "unknown") or "unknown")
        source_rank_confidence = source_rank.get("confidence")
        if source_rank_confidence is None:
            source_rank_confidence = source_rank.get("rank_confidence")

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        rejected: List[Dict[str, Any]] = []
        for cand in stock_candidates if isinstance(stock_candidates, list) else []:
            if not isinstance(cand, dict):
                continue
            symbol = str(cand.get("symbol", "")).strip().upper()
            source = str(cand.get("source", "")).strip()
            role = str(cand.get("role") or self._candidate_role(cand)).strip()
            relation = str(cand.get("relation") or self._candidate_relation(cand)).strip()
            reject_reason = self._candidate_missing_provenance_reason(cand)
            provenance_entry = {
                "symbol": symbol,
                "source": source or "unknown",
                "role": role or "unknown",
                "relation": relation or "derived",
                "event_id": str(cand.get("event_id") or event_id),
                "candidate_origin": str(cand.get("candidate_origin") or mapping_source),
                "source_rank": str(cand.get("source_rank") or source_rank_rank),
                "source_rank_confidence": cand.get("source_rank_confidence", source_rank_confidence),
            }
            if reject_reason == "missing_symbol":
                rejected.append(
                    {
                        "symbol": "",
                        "status": "rejected",
                        "source": provenance_entry["source"],
                        "role": provenance_entry["role"],
                        "relation": provenance_entry["relation"],
                        "event_id": provenance_entry["event_id"],
                        "candidate_origin": provenance_entry["candidate_origin"],
                        "source_rank": provenance_entry["source_rank"],
                        "source_rank_confidence": provenance_entry["source_rank_confidence"],
                        "reject_reason": reject_reason,
                        "downgrade_reason": None,
                        "provenance": [provenance_entry],
                        "compatibility_surface": "candidate_envelope",
                    }
                )
                continue
            if reject_reason in {"missing_source", "missing_role", "missing_relation", "missing_event_id"}:
                rejected.append(
                    {
                        "symbol": symbol,
                        "status": "rejected",
                        "source": provenance_entry["source"],
                        "role": provenance_entry["role"],
                        "relation": provenance_entry["relation"],
                        "event_id": provenance_entry["event_id"],
                        "candidate_origin": provenance_entry["candidate_origin"],
                        "source_rank": provenance_entry["source_rank"],
                        "source_rank_confidence": provenance_entry["source_rank_confidence"],
                        "reject_reason": reject_reason,
                        "downgrade_reason": None,
                        "provenance": [provenance_entry],
                        "compatibility_surface": "candidate_envelope",
                    }
                )
                continue
            grouped.setdefault(symbol, []).append(provenance_entry)

        envelopes: List[Dict[str, Any]] = []
        for symbol, provenance_list in grouped.items():
            primary = provenance_list[0]
            source = str(primary.get("source", "")).strip() or "unknown"
            role = str(primary.get("role", "")).strip() or "unknown"
            relation = str(primary.get("relation", "")).strip() or "derived"
            event_id_value = str(primary.get("event_id") or event_id).strip() or event_id
            candidate_origin = str(primary.get("candidate_origin") or mapping_source).strip() or mapping_source
            status = "candidate"
            reject_reason = None
            downgrade_reason = None

            if source == "unknown" or not event_id_value:
                status = "rejected"
                reject_reason = "missing_critical_provenance"
            elif any(p.get("source", "unknown") == "unknown" for p in provenance_list) or any(
                not str(p.get("relation", "")).strip() for p in provenance_list
            ):
                status = "downgraded"
                downgrade_reason = "partial_provenance"

            envelopes.append(
                {
                    "symbol": symbol,
                    "source": source,
                    "role": role,
                    "relation": relation,
                    "event_id": event_id_value,
                    "candidate_origin": candidate_origin,
                    "source_rank": primary.get("source_rank", source_rank_rank),
                    "source_rank_confidence": primary.get("source_rank_confidence", source_rank_confidence),
                    "status": status,
                    "reject_reason": reject_reason,
                    "downgrade_reason": downgrade_reason,
                    "provenance": provenance_list,
                    "compatibility_surface": "candidate_envelope",
                }
            )

        return {
            "status": "shadow_only",
            "compatibility_surface": "candidate_envelope",
            "trace_id": trace_id,
            "event_id": event_id,
            "candidate_origin": mapping_source,
            "source_rank": dict(source_rank),
            "candidate_count": len(envelopes) + len(rejected),
            "envelopes": envelopes + rejected,
        }

    @staticmethod
    def _normalize_entity_symbol(symbol: Any) -> str:
        return str(symbol or "").strip().upper()

    def _load_entity_alias_registry(self) -> tuple[Dict[str, str], set[str]]:
        """Load an optional alias registry for deterministic entity normalization.

        The default runtime registry is empty. The production path here only does
        strip / uppercase / validity checks. Ambiguous / not_found behavior is
        registry-backed extension scaffolding, not enabled by default in PR147.
        Any future registry input path must ship with dedicated config and tests.
        """
        return {}, set()

    def _build_entity_resolution_surface(
        self,
        candidate_generation_out: Dict[str, Any],
        *,
        candidate_envelope_out: Dict[str, Any] | None,
        trace_id: str,
        event_id: str,
        source_rank: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a shadow-only Entity Resolver compatibility surface."""
        alias_to_canonical, alias_conflicts = self._load_entity_alias_registry()
        alias_to_canonical = dict(alias_to_canonical or {})
        alias_conflicts = set(alias_conflicts or set())
        envelope_rejections: Dict[str, str] = {}
        if isinstance(candidate_envelope_out, dict):
            for item in candidate_envelope_out.get("envelopes", []) or []:
                if not isinstance(item, dict):
                    continue
                if item.get("status") != "rejected":
                    continue
                envelope_symbol = self._normalize_entity_symbol(item.get("symbol"))
                if envelope_symbol and envelope_symbol not in envelope_rejections:
                    envelope_rejections[envelope_symbol] = str(item.get("reject_reason") or "rejected")

        input_surface = "conduction_candidate_generation"
        raw_entries = list(candidate_generation_out.get("stock_candidates", []) or [])

        entries: List[Dict[str, Any]] = []
        for cand in raw_entries:
            if not isinstance(cand, dict):
                continue
            original_symbol = str(cand.get("symbol", "")).strip()
            symbol = self._normalize_entity_symbol(original_symbol)
            provenance = cand.get("provenance")
            if isinstance(provenance, list) and provenance:
                provenance_list = deepcopy(provenance)
            else:
                provenance_list = [
                    {
                        "symbol": symbol,
                        "source": str(cand.get("source", "")).strip() or "unknown",
                        "role": str(cand.get("role", "")).strip() or "unknown",
                        "relation": str(cand.get("relation", "")).strip() or "derived",
                        "event_id": str(cand.get("event_id") or event_id),
                        "candidate_origin": str(cand.get("candidate_origin") or candidate_generation_out.get("mapping_source") or "conduction_candidate_generation"),
                        "source_rank": str(cand.get("source_rank") or source_rank.get("rank", "unknown") or "unknown"),
                    }
                ]

            source = str(cand.get("source") or (provenance_list[0].get("source") if provenance_list else "") or "").strip()
            role = str(cand.get("role") or (provenance_list[0].get("role") if provenance_list else "") or "").strip()
            relation = str(cand.get("relation") or (provenance_list[0].get("relation") if provenance_list else "") or "").strip()
            event_id_value = str(cand.get("event_id") or (provenance_list[0].get("event_id") if provenance_list else event_id) or event_id).strip() or event_id
            candidate_origin = str(cand.get("candidate_origin") or (provenance_list[0].get("candidate_origin") if provenance_list else candidate_generation_out.get("mapping_source") or "conduction_candidate_generation") or "conduction_candidate_generation").strip() or "conduction_candidate_generation"

            resolver_status = "resolved"
            reject_reason = None
            canonical_symbol = symbol

            if not original_symbol:
                resolver_status = "rejected"
                reject_reason = "missing_symbol"
            elif not ConductionMapper._is_valid_symbol(symbol):
                resolver_status = "rejected"
                reject_reason = "invalid_symbol"
            elif symbol in alias_conflicts:
                resolver_status = "ambiguous"
                reject_reason = "ambiguous_identity"
            elif alias_to_canonical:
                canonical_symbol = alias_to_canonical.get(symbol, "")
                if canonical_symbol:
                    canonical_symbol = self._normalize_entity_symbol(canonical_symbol)
                else:
                    resolver_status = "not_found"
                    reject_reason = "not_found"
                    canonical_symbol = symbol
            if symbol in envelope_rejections and resolver_status != "rejected":
                resolver_status = "rejected"
                reject_reason = envelope_rejections[symbol]

            if cand.get("status") == "rejected" and not reject_reason:
                resolver_status = "rejected"
                reject_reason = str(cand.get("reject_reason") or "rejected")

            entries.append(
                {
                    "symbol": symbol,
                    "canonical_symbol": canonical_symbol or symbol,
                    "original_symbol": original_symbol,
                    "resolver_status": resolver_status,
                    "reject_reason": reject_reason,
                    "candidate_origin": candidate_origin,
                    "source": source or "unknown",
                    "role": role or "unknown",
                    "relation": relation or "derived",
                    "event_id": event_id_value,
                    "provenance": provenance_list,
                    "compatibility_surface": "entity_resolution",
                }
            )

        return {
            "status": "shadow_only",
            "compatibility_surface": "entity_resolution",
            "input_surface": input_surface,
            "trace_id": trace_id,
            "event_id": event_id,
            "candidate_origin": str(candidate_generation_out.get("mapping_source") or "conduction_candidate_generation"),
            "source_rank": dict(source_rank),
            "resolver_count": len(entries),
            "resolved_count": sum(1 for item in entries if item.get("resolver_status") == "resolved"),
            "ambiguous_count": sum(1 for item in entries if item.get("resolver_status") == "ambiguous"),
            "not_found_count": sum(1 for item in entries if item.get("resolver_status") == "not_found"),
            "rejected_count": sum(1 for item in entries if item.get("resolver_status") == "rejected"),
            "entries": entries,
        }

    def _candidate_envelope_final_symbols(self, candidate_envelope_out: Dict[str, Any]) -> List[str]:
        if not isinstance(candidate_envelope_out, dict):
            return []
        symbols = [
            str(item.get("symbol", "")).strip().upper()
            for item in candidate_envelope_out.get("envelopes", [])
            if isinstance(item, dict) and item.get("status") == "candidate"
        ]
        return self._dedupe_ordered_symbols(symbols)

    def _entity_resolution_final_symbols(self, entity_resolution_out: Dict[str, Any] | None) -> List[str]:
        if not isinstance(entity_resolution_out, dict):
            return []
        entries = entity_resolution_out.get("entries", [])
        if not isinstance(entries, list):
            return []
        symbols: List[str] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            if item.get("resolver_status") != "resolved":
                continue
            canonical_symbol = str(item.get("canonical_symbol", "")).strip().upper()
            if canonical_symbol:
                symbols.append(canonical_symbol)
        return self._dedupe_ordered_symbols(symbols)

    @staticmethod
    def _index_entity_resolution_entries(entity_resolution_out: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        if not isinstance(entity_resolution_out, dict):
            return indexed
        for item in entity_resolution_out.get("entries", []) or []:
            if not isinstance(item, dict):
                continue
            for key in (item.get("symbol"), item.get("original_symbol"), item.get("canonical_symbol")):
                normalized = str(key or "").strip().upper()
                if normalized and normalized not in indexed:
                    indexed[normalized] = deepcopy(item)
        return indexed

    @staticmethod
    def _index_candidate_envelope_entries(candidate_envelope_out: Dict[str, Any] | None) -> Dict[str, List[Dict[str, Any]]]:
        indexed: Dict[str, List[Dict[str, Any]]] = {}
        if not isinstance(candidate_envelope_out, dict):
            return indexed
        for item in candidate_envelope_out.get("envelopes", []) or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            indexed.setdefault(symbol, []).append(deepcopy(item))
        return indexed

    def _build_unified_candidate_pool_surface(
        self,
        candidate_generation_out: Dict[str, Any],
        *,
        candidate_envelope_out: Dict[str, Any] | None,
        entity_resolution_out: Dict[str, Any] | None,
        trace_id: str,
        event_id: str,
        source_rank: Dict[str, Any],
        enable_multisource_merge: bool,
    ) -> Dict[str, Any]:
        """Create a shadow-only unified candidate pool compatibility surface."""
        raw_candidates = list(candidate_generation_out.get("stock_candidates", []) or [])
        entity_resolution_index = self._index_entity_resolution_entries(entity_resolution_out)
        envelope_index = self._index_candidate_envelope_entries(candidate_envelope_out)
        has_entity_resolution = isinstance(entity_resolution_out, dict) and isinstance(entity_resolution_out.get("entries"), list)
        effective_multisource_merge = bool(enable_multisource_merge and has_entity_resolution)

        records: List[Dict[str, Any]] = []
        for cand in raw_candidates:
            if not isinstance(cand, dict):
                continue
            symbol = self._normalize_entity_symbol(cand.get("symbol"))
            provenance = cand.get("provenance")
            if isinstance(provenance, list) and provenance:
                provenance_list = deepcopy(provenance)
            else:
                provenance_list = [
                    {
                        "symbol": symbol,
                        "source": str(cand.get("source", "")).strip() or "unknown",
                        "role": str(cand.get("role", "")).strip() or "unknown",
                        "relation": str(cand.get("relation", "")).strip() or "derived",
                        "event_id": str(cand.get("event_id") or event_id),
                        "candidate_origin": str(cand.get("candidate_origin") or candidate_generation_out.get("mapping_source") or "conduction_candidate_generation"),
                        "source_rank": str(cand.get("source_rank") or source_rank.get("rank", "unknown") or "unknown"),
                    }
                ]

            source = str(cand.get("source") or (provenance_list[0].get("source") if provenance_list else "") or "").strip() or "unknown"
            role = str(cand.get("role") or (provenance_list[0].get("role") if provenance_list else "") or "").strip() or "unknown"
            relation = str(cand.get("relation") or (provenance_list[0].get("relation") if provenance_list else "") or "").strip() or "derived"
            event_id_value = str(cand.get("event_id") or (provenance_list[0].get("event_id") if provenance_list else event_id) or event_id).strip() or event_id
            candidate_origin = str(cand.get("candidate_origin") or (provenance_list[0].get("candidate_origin") if provenance_list else candidate_generation_out.get("mapping_source") or "conduction_candidate_generation") or "conduction_candidate_generation").strip() or "conduction_candidate_generation"

            entity_resolution_entry = entity_resolution_index.get(symbol, {}) if has_entity_resolution else {}
            envelope_entries = list(envelope_index.get(symbol, []) or [])
            canonical_symbol = symbol
            resolver_status = "missing_entity_resolution"
            reject_reason = None
            downgrade_reason = None
            status = "downgraded"

            if has_entity_resolution and entity_resolution_entry:
                canonical_symbol = self._normalize_entity_symbol(
                    entity_resolution_entry.get("canonical_symbol") or symbol
                ) or symbol
                resolver_status = str(entity_resolution_entry.get("resolver_status") or ("resolved" if symbol else "rejected"))
                reject_reason = str(entity_resolution_entry.get("reject_reason") or "").strip() or None
                status = "candidate"

            envelope_reject_reason = None
            envelope_downgrade_reason = None
            envelope_statuses = [str(item.get("status", "")).strip().lower() for item in envelope_entries]
            if envelope_entries:
                envelope_reject_reason = next(
                    (str(item.get("reject_reason") or "").strip() for item in envelope_entries if str(item.get("reject_reason") or "").strip()),
                    None,
                )
                envelope_downgrade_reason = next(
                    (str(item.get("downgrade_reason") or "").strip() for item in envelope_entries if str(item.get("downgrade_reason") or "").strip()),
                    None,
                )

            if any(status_value == "rejected" for status_value in envelope_statuses):
                status = "rejected"
                reject_reason = envelope_reject_reason or reject_reason or "rejected"
            elif resolver_status == "rejected":
                status = "rejected"
                reject_reason = reject_reason or envelope_reject_reason or "rejected"
            elif resolver_status in {"ambiguous", "not_found"}:
                status = "downgraded"
                downgrade_reason = reject_reason or resolver_status
            elif any(status_value == "downgraded" for status_value in envelope_statuses):
                status = "downgraded"
                downgrade_reason = envelope_downgrade_reason or reject_reason or "partial_provenance"

            if not has_entity_resolution:
                status = "rejected" if any(status_value == "rejected" for status_value in envelope_statuses) else "downgraded"
                resolver_status = "rejected" if status == "rejected" else "missing_entity_resolution"
                if status == "rejected":
                    reject_reason = envelope_reject_reason or reject_reason or "missing_entity_resolution"
                    downgrade_reason = None
                else:
                    downgrade_reason = "missing_entity_resolution"
                    reject_reason = None

            if status == "candidate" and cand.get("status") == "rejected":
                status = "rejected"
                reject_reason = str(cand.get("reject_reason") or "rejected")

            records.append(
                {
                    "symbol": symbol,
                    "canonical_symbol": canonical_symbol,
                    "source": source,
                    "role": role,
                    "relation": relation,
                    "event_id": event_id_value,
                    "candidate_origin": candidate_origin,
                    "source_rank": dict(source_rank),
                    "provenance": provenance_list,
                    "resolver_status": resolver_status,
                    "reject_reason": reject_reason,
                    "downgrade_reason": downgrade_reason,
                    "status": status,
                    "source_list": [source],
                    "role_list": [role],
                    "relation_list": [relation],
                    "event_ids": [event_id_value],
                }
            )

        if not effective_multisource_merge:
            items = [
                {
                    **record,
                    "merge_status": "rejected"
                    if record["status"] == "rejected"
                    else "downgraded"
                    if record["status"] == "downgraded"
                    else "unmerged",
                }
                for record in records
            ]
        else:
            grouped: List[Dict[str, Any]] = []
            grouped_index: Dict[str, Dict[str, Any]] = {}
            for record in records:
                key = str(record.get("canonical_symbol", "")).strip().upper() or str(record.get("symbol", "")).strip().upper()
                if key not in grouped_index:
                    merged = deepcopy(record)
                    grouped_index[key] = merged
                    grouped.append(merged)
                    continue
                merged = grouped_index[key]
                merged["source_list"].append(record["source"])
                merged["role_list"].append(record["role"])
                merged["relation_list"].append(record["relation"])
                merged["event_ids"].append(record["event_id"])
                merged["provenance"].extend(deepcopy(record["provenance"]))
                if merged["candidate_origin"] == "conduction_candidate_generation" and record["candidate_origin"] != "conduction_candidate_generation":
                    merged["candidate_origin"] = record["candidate_origin"]
                if merged["resolver_status"] == "resolved" and record["resolver_status"] != "resolved":
                    merged["resolver_status"] = record["resolver_status"]
                if merged["status"] == "candidate" and record["status"] != "candidate":
                    merged["status"] = record["status"]
                if merged["status"] != "rejected" and record["status"] == "rejected":
                    merged["status"] = "rejected"
                    merged["reject_reason"] = record["reject_reason"] or merged.get("reject_reason") or "rejected"
                elif merged["status"] == "candidate" and record["status"] == "downgraded":
                    merged["status"] = "downgraded"
                    merged["downgrade_reason"] = record["downgrade_reason"] or merged.get("downgrade_reason") or "partial_provenance"
                if record["status"] == "candidate" and merged.get("status") == "candidate":
                    pass
                if merged.get("status") == "downgraded" and not merged.get("downgrade_reason") and record.get("downgrade_reason"):
                    merged["downgrade_reason"] = record["downgrade_reason"]
                if merged.get("status") == "rejected" and not merged.get("reject_reason") and record.get("reject_reason"):
                    merged["reject_reason"] = record["reject_reason"]

            items = grouped

        for item in items:
            item["source_list"] = self._dedupe_ordered_text(item.get("source_list", []))
            item["role_list"] = self._dedupe_ordered_text(item.get("role_list", []))
            item["relation_list"] = self._dedupe_ordered_text(item.get("relation_list", []))
            item["event_ids"] = self._dedupe_ordered_text(item.get("event_ids", []))
            if item.get("status") == "candidate":
                item["merge_status"] = "merged" if len(item.get("provenance", [])) > 1 else "unmerged"
            elif item.get("status") == "downgraded":
                item["merge_status"] = "downgraded"
            else:
                item["merge_status"] = "rejected"

        return {
            "status": "shadow_only",
            "compatibility_surface": "unified_candidate_pool",
            "trace_id": trace_id,
            "event_id": event_id,
            "source_rank": dict(source_rank),
            "item_count": len(items),
            "merged_count": sum(1 for item in items if item.get("merge_status") == "merged"),
            "rejected_count": sum(1 for item in items if item.get("status") == "rejected"),
            "downgraded_count": sum(1 for item in items if item.get("status") == "downgraded"),
            "items": items,
        }

    def _run_conduction_candidate_generation(
        self,
        *,
        event_object: Dict[str, Any],
        payload: Dict[str, Any],
        lifecycle_out: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.conduction.run(
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

    @staticmethod
    def _run_conduction_final_selection(
        *,
        candidate_generation_out: Dict[str, Any],
        enable_v5_shadow_output: bool,
        enable_replace_legacy_output: bool,
    ) -> Dict[str, Any]:
        # Stage8A-Impl-1 stays shadow-only: pass-through selection metadata only.
        stock_candidates = candidate_generation_out.get("stock_candidates", [])
        shadow_final_recommended = [
            str(item.get("symbol")).strip().upper()
            for item in stock_candidates
            if isinstance(item, dict) and str(item.get("symbol", "")).strip()
        ]
        return {
            # Phase-0 freeze: only conduction_final_selection may emit this interface.
            "final_recommended_stocks": shadow_final_recommended,
            "shadow_only": bool(enable_v5_shadow_output and not enable_replace_legacy_output),
            "selection_mode": "shadow_passthrough_impl1",
            "decision_reason": "impl1_shadow_passthrough",
        }

    def _build_semantic_full_peer_expansion_surface(
        self,
        *,
        semantic_out: Dict[str, Any],
        candidate_generation_out: Dict[str, Any],
        final_recommended_stocks: List[str],
        source_rank: Dict[str, Any],
        trace_id: str,
        event_id: str,
    ) -> Dict[str, Any]:
        """Build a shadow-only semantic peer expansion surface for Stage8A Impl-4."""
        anchor_stocks = self._dedupe_ordered_symbols(final_recommended_stocks)
        anchor_symbol = anchor_stocks[0] if anchor_stocks else ""
        semantic_candidates = self._dedupe_ordered_symbols(
            semantic_out.get("recommended_stocks", []) if isinstance(semantic_out, dict) else []
        )
        fallback_candidates = self._dedupe_ordered_symbols(
            [
                str(item.get("symbol", "")).strip().upper()
                for item in candidate_generation_out.get("stock_candidates", [])
                if isinstance(item, dict) and str(item.get("symbol", "")).strip()
            ]
        )

        peer_symbols: List[str] = []
        for symbol in semantic_candidates + fallback_candidates:
            if symbol and symbol not in anchor_stocks and symbol not in peer_symbols:
                peer_symbols.append(symbol)

        peer_candidates: List[Dict[str, Any]] = []
        for symbol in peer_symbols:
            semantic_confidence = float(semantic_out.get("confidence", 0.0) or 0.0)
            relation_evidence = {
                "evidence_type": "same_sector_peer",
                "evidence_value": {
                    "anchor_symbol": anchor_symbol or symbol,
                    "peer_symbol": symbol,
                    "semantic_event_type": str(semantic_out.get("event_type", "unknown")),
                    "transmission_candidates": list(semantic_out.get("transmission_candidates", []) or []),
                },
                "evidence_source": "semantic_full_prompt",
                "evidence_text": (
                    f"Peer {symbol} is derived from semantic full expansion anchored on {anchor_symbol or symbol}"
                ),
                "confidence": semantic_confidence,
                "audit_note": "shadow_only_peer_candidate_contract",
            }
            peer_candidates.append(
                {
                    "symbol": symbol,
                    "canonical_symbol": symbol,
                    "peer_symbol": symbol,
                    "anchor_symbol": anchor_symbol or symbol,
                    "relation_type": "same_sector_peer",
                    "relation_evidence": relation_evidence,
                    "relation_evidence_source": "semantic_full_prompt",
                    "event_id": event_id,
                    "trace_id": trace_id,
                    "candidate_origin": "semantic_full_peer_expansion",
                    "source": "semantic_full_peer_expansion",
                    "source_rank": dict(source_rank),
                    "semantic_confidence": semantic_confidence,
                    "peer_confidence": semantic_confidence,
                    "resolver_status": "resolved",
                    "status": "candidate",
                    "reject_reason": None,
                    "downgrade_reason": None,
                    "is_final": False,
                    "non_final": True,
                }
            )

        return {
            "status": "shadow_only",
            "compatibility_surface": "semantic_full_peer_expansion",
            "trace_id": trace_id,
            "event_id": event_id,
            "prompt_contract": {
                "schema_version": "stage8a.peer_prompt_contract.v1",
                "required_output_fields": [
                    "symbol",
                    "canonical_symbol",
                    "peer_symbol",
                    "anchor_symbol",
                    "relation_type",
                    "relation_evidence",
                    "relation_evidence_source",
                    "event_id",
                    "trace_id",
                    "candidate_origin",
                    "source",
                    "source_rank",
                    "semantic_confidence",
                    "peer_confidence",
                    "resolver_status",
                    "status",
                    "reject_reason",
                    "downgrade_reason",
                    "is_final",
                ],
                "relation_evidence_required_fields": [
                    "evidence_type",
                    "evidence_value",
                    "evidence_source",
                    "evidence_text",
                    "confidence",
                ],
                "peer_validation_input_fields": [
                    "peer_symbol",
                    "anchor_symbol",
                    "canonical_symbol",
                    "relation_type",
                    "relation_evidence",
                    "relation_evidence_source",
                    "semantic_confidence",
                    "peer_confidence",
                    "source_rank",
                    "event_id",
                    "trace_id",
                    "candidate_origin",
                    "status",
                    "reject_reason",
                    "downgrade_reason",
                    "is_final",
                ],
                "relation_evidence_required": True,
                "mode": "shadow_only",
            },
            "anchor_stocks": anchor_stocks,
            "anchor_symbol": anchor_symbol or None,
            "peer_candidates": peer_candidates,
            "peer_candidate_count": len(peer_candidates),
            "validated_peer_candidates": [],
            "rejected_peer_candidates": [],
        }

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
        # Stage8A-Impl-1 boundary:
        # - flags can independently disable risky modules for rollback drills
        # - legacy replacement remains hard-blocked in Impl-1
        loaded_flags = self._load_feature_flags()
        enable_v5_shadow_output = bool(loaded_flags.get("enable_v5_shadow_output", True))
        enable_source_metadata_propagation = bool(loaded_flags.get("enable_source_metadata_propagation", False))
        enable_candidate_envelope = bool(loaded_flags.get("enable_candidate_envelope", False))
        enable_entity_resolver = bool(loaded_flags.get("enable_entity_resolver", False))
        enable_unified_candidate_pool = bool(loaded_flags.get("enable_unified_candidate_pool", False))
        enable_multisource_merge = bool(loaded_flags.get("enable_multisource_merge", False))
        enable_semantic_full_peer_expansion = bool(loaded_flags.get("enable_semantic_full_peer_expansion", False))
        # Impl-1 default must be enabled even if config defaults are still conservative.
        # Flags remain independently switchable via request payload for rollback drills.
        if "enable_semantic_prepass" in payload:
            enable_semantic_prepass = self._coerce_bool(
                payload.get("enable_semantic_prepass"),
                loaded_flags.get("enable_semantic_prepass", True),
            )
        else:
            enable_semantic_prepass = True
        if "enable_conduction_split" in payload:
            enable_conduction_split = self._coerce_bool(
                payload.get("enable_conduction_split"),
                loaded_flags.get("enable_conduction_split", True),
            )
        else:
            enable_conduction_split = True
        requested_replace_legacy = self._coerce_bool(
            payload.get("enable_replace_legacy_output"),
            loaded_flags.get("enable_replace_legacy_output", False),
        )
        # Impl-1 never allows legacy replacement.
        enable_replace_legacy_output = False

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

        semantic_out = self.semantic.analyze(event_object["headline"], payload.get("summary", event_object["headline"]))
        if enable_semantic_prepass:
            semantic_prepass = self._build_semantic_prepass_contract(
                semantic_out=semantic_out,
                headline=event_object.get("headline", ""),
            )
            self._log_pipeline_stage(
                trace_id=trace_id,
                event_id=event_id,
                request_id=request_id,
                batch_id=batch_id,
                event_hash=event_hash,
                stage_seq=4,
                stage="semantic_prepass",
                status="success",
                details={
                    "route_type": semantic_prepass.get("route_type"),
                    "semantic_confidence": semantic_prepass.get("semantic_confidence"),
                },
            )
        else:
            semantic_prepass = {
                "route_type": "unknown",
                "event_type": "unknown",
                "event_direction": "neutral",
                "anchor_entities": [],
                "semantic_confidence": 0.0,
                "market_hint": "UNKNOWN",
                "needs_full_semantic": True,
                "prepass_latency_ms": 0,
                "status": "disabled",
            }
            self._log_pipeline_stage(
                trace_id=trace_id,
                event_id=event_id,
                request_id=request_id,
                batch_id=batch_id,
                event_hash=event_hash,
                stage_seq=4,
                stage="semantic_prepass",
                status="skipped",
                details={"reason": "feature_flag_disabled"},
            )

        if enable_conduction_split:
            conduction_candidate_generation_out = self._run_conduction_candidate_generation(
                event_object=event_object,
                payload=payload,
                lifecycle_out=lifecycle_out,
            )
        else:
            conduction_candidate_generation_out = self.conduction.run(
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
        if enable_source_metadata_propagation:
            conduction_candidate_generation_out = self._propagate_candidate_metadata(
                conduction_candidate_generation_out,
                trace_id=trace_id,
                event_id=event_id,
                source_rank=source_rank,
            )
        candidate_envelope_out = (
            self._build_candidate_envelope_surface(
                conduction_candidate_generation_out,
                trace_id=trace_id,
                event_id=event_id,
                source_rank=source_rank,
            )
            if enable_candidate_envelope
            else None
        )
        entity_resolution_out = (
            self._build_entity_resolution_surface(
                conduction_candidate_generation_out,
                candidate_envelope_out=candidate_envelope_out,
                trace_id=trace_id,
                event_id=event_id,
                source_rank=source_rank,
            )
            if enable_entity_resolver
            else None
        )
        unified_candidate_pool_out = (
            self._build_unified_candidate_pool_surface(
                conduction_candidate_generation_out,
                candidate_envelope_out=candidate_envelope_out,
                entity_resolution_out=entity_resolution_out,
                trace_id=trace_id,
                event_id=event_id,
                source_rank=source_rank,
                enable_multisource_merge=enable_multisource_merge,
            )
            if enable_unified_candidate_pool
            else None
        )
        conduction_out = conduction_candidate_generation_out
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=5,
            stage="conduction",
            status="success",
            details={"confidence": conduction_out.get("confidence"), "path_len": len(conduction_out.get("conduction_path", []))},
        )

        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=6,
            stage="conduction_candidate_generation",
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
        provenance_record = self._build_market_data_provenance_record(
            trace_id=trace_id,
            request_id=request_id,
            batch_id=batch_id,
            event_id=event_id,
            event_hash=event_hash,
            validation_out=validation_out,
            payload=payload,
            derived_symbols_requested=derived_symbols_requested,
            derived_symbols_returned=derived_symbols_returned,
        )
        self._upsert_jsonl_record(
            self.market_data_provenance_log_path,
            provenance_record,
            ("trace_id", "request_id", "batch_id", "event_hash"),
        )
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=7,
            stage="market_validation",
            status="success",
            details={
                "market_data_source": validation_out.get("market_data_source"),
                "market_data_stale": bool(validation_out.get("market_data_stale", False)),
                "market_data_default_used": bool(validation_out.get("market_data_default_used", False)),
                "market_data_fallback_used": bool(validation_out.get("market_data_fallback_used", False)),
            },
        )

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
            stage_seq=8,
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
            stage_seq=9,
            stage="path_adjudication",
            status="success",
            details={"primary_path": (path_out.get("primary_path") or {}).get("path_text", "undetermined")},
        )

        conduction_final_selection_out = self._run_conduction_final_selection(
            candidate_generation_out=conduction_candidate_generation_out,
            enable_v5_shadow_output=enable_v5_shadow_output,
            enable_replace_legacy_output=enable_replace_legacy_output,
        )
        if enable_entity_resolver and entity_resolution_out is not None:
            candidate_envelope_symbols = self._entity_resolution_final_symbols(entity_resolution_out)
            conduction_final_selection_out = {
                **conduction_final_selection_out,
                "final_recommended_stocks": candidate_envelope_symbols,
            }
        elif enable_candidate_envelope and candidate_envelope_out is not None:
            candidate_envelope_symbols = self._candidate_envelope_final_symbols(candidate_envelope_out)
            conduction_final_selection_out = {
                **conduction_final_selection_out,
                "final_recommended_stocks": candidate_envelope_symbols,
            }
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=10,
            stage="conduction_final_selection",
            status="success",
            details={
                "shadow_only": conduction_final_selection_out.get("shadow_only"),
                "final_count": len(conduction_final_selection_out.get("final_recommended_stocks", [])),
            },
        )
        semantic_full_peer_expansion_out = (
            self._build_semantic_full_peer_expansion_surface(
                semantic_out=semantic_out,
                candidate_generation_out=conduction_candidate_generation_out,
                final_recommended_stocks=list(conduction_final_selection_out.get("final_recommended_stocks", [])),
                source_rank=source_rank,
                trace_id=trace_id,
                event_id=event_id,
            )
            if enable_semantic_full_peer_expansion
            else None
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
            stage_seq=11,
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
            "semantic_prepass": semantic_prepass,
            "event_object_contract": event_contract,
            "path_adjudication": path_out,
            "conduction_candidate_generation": conduction_candidate_generation_out,
            "conduction_final_selection": {
                "shadow_only": bool(conduction_final_selection_out.get("shadow_only", True)),
                "selection_mode": str(conduction_final_selection_out.get("selection_mode", "shadow_passthrough_impl1")),
                "decision_reason": str(conduction_final_selection_out.get("decision_reason", "impl1_shadow_passthrough")),
                "final_recommended_stocks": list(conduction_final_selection_out.get("final_recommended_stocks", [])),
            },
            **({"candidate_envelope": candidate_envelope_out} if candidate_envelope_out is not None else {}),
            **({"entity_resolution": entity_resolution_out} if entity_resolution_out is not None else {}),
            **({"unified_candidate_pool": unified_candidate_pool_out} if unified_candidate_pool_out is not None else {}),
            **({"semantic_full_peer_expansion": semantic_full_peer_expansion_out} if semantic_full_peer_expansion_out is not None else {}),
            "signal": signal_out,
            "v5_shadow": {
                "enable_v5_shadow_output": enable_v5_shadow_output,
                "enable_replace_legacy_output": enable_replace_legacy_output,
                "enable_semantic_prepass": enable_semantic_prepass,
                "enable_conduction_split": enable_conduction_split,
                "enable_source_metadata_propagation": enable_source_metadata_propagation,
                "enable_candidate_envelope": enable_candidate_envelope,
                "enable_entity_resolver": enable_entity_resolver,
                "enable_semantic_full_peer_expansion": enable_semantic_full_peer_expansion,
                "replace_legacy_requested": requested_replace_legacy,
                "comparison_status": "observe_only" if enable_v5_shadow_output and not enable_replace_legacy_output else "disabled",
                "legacy_recommended_stocks": [
                    str(item.get("symbol")).strip().upper()
                    for item in conduction_out.get("stock_candidates", [])
                    if isinstance(item, dict) and str(item.get("symbol", "")).strip()
                ],
                "v5_shadow_final_recommended_stocks": list(conduction_final_selection_out.get("final_recommended_stocks", [])),
                "old_vs_v5_shadow_diff": {
                    "legacy_count": len(conduction_out.get("stock_candidates", [])),
                    "v5_shadow_count": len(conduction_final_selection_out.get("final_recommended_stocks", [])),
                },
            },
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
            driver_type = str(item.get("driver_type", "")).strip().lower()
            if driver_type == "legacy_event_broadcast":
                sector_score_source = "legacy_event_broadcast"
            elif driver_type in {"template", "semantic_sector"}:
                sector_score_source = "semantic_sector"
            elif driver_type in {"beta_alpha", "rule_adjusted", "tier1_weight"}:
                sector_score_source = "rule_adjusted"
            else:
                sector_score_source = "sector_marginal"
            try:
                raw_confidence = float(item.get("confidence", conduction_out.get("confidence", 0)))
            except (TypeError, ValueError):
                raw_confidence = float(conduction_out.get("confidence", 0) or 0.0)
            confidence_value = raw_confidence / 100.0 if raw_confidence > 1.0 else raw_confidence
            sectors.append(
                {
                    "name": item.get("sector", "未知板块"),
                    "direction": "LONG" if item.get("direction") == "benefit" else "SHORT",
                    "impact_score": round(min(1.0, max(0.0, float(item.get("impact_score", 0.0)))), 2),
                    "confidence": round(min(1.0, max(0.0, confidence_value)), 2),
                    "sector_score_source": sector_score_source,
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

        raw_score = signal_out.get("score")
        normalized_score = float(raw_score) / 100.0 if raw_score is not None else None

        path_quality_in = {
            "path_confidence": normalized_score,
            "validation_checks": validation_out.get("checks"),
            "relative_direction_score": signal_out.get("relative_direction_score"),
            "absolute_direction": signal_out.get("absolute_direction"),
            "driver_confidence": signal_out.get("driver_confidence"),
            "gap_score": signal_out.get("gap_score"),
            "execution_confidence": signal_out.get("execution_confidence"),
        }
        path_quality_out = self.path_quality_evaluator.run(path_quality_in)
        if path_quality_out.status == ModuleStatus.SUCCESS:
            analysis_out["path_quality_eval"] = path_quality_out.data
        else:
            analysis_out["path_quality_eval_status"] = "failed"
            analysis_out["path_quality_eval_errors"] = path_quality_out.errors
            self._log_pipeline_stage(
                trace_id=trace_id,
                event_id=event_id,
                request_id=request_id,
                batch_id=batch_id,
                event_hash=event_hash,
                stage_seq=11,
                stage="path_quality_eval",
                status="failed",
                details={"errors": path_quality_out.errors},
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
        enriched_record = self._build_market_data_provenance_record(
            trace_id=trace_id,
            request_id=request_id,
            batch_id=batch_id,
            event_id=event_id,
            event_hash=event_hash,
            validation_out=validation_out,
            payload=payload,
            derived_symbols_requested=derived_symbols_requested,
            derived_symbols_returned=derived_symbols_returned,
            provider_meta=provider_meta,
        )
        self._upsert_jsonl_record(
            self.market_data_provenance_log_path,
            enriched_record,
            ("trace_id", "request_id", "batch_id", "event_hash"),
        )
        self._log_pipeline_stage(
            trace_id=trace_id,
            event_id=event_id,
            request_id=request_id,
            batch_id=batch_id,
            event_hash=event_hash,
            stage_seq=12,
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
            stage_seq=13,
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
