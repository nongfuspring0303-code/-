#!/usr/bin/env python3
"""
Workflow runner for T5.1.
Chain: SignalScorer -> LiquidityChecker -> RiskGatekeeper -> PositionSizer -> ExitManager
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import concurrent.futures
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
try:
    from theme_obs.theme_observability import ThemeObservabilityLogger
except ImportError:
    import logging
    logging.error("OBSERVABILITY_MODULE_MISSING: theme_obs.theme_observability failed to load. Observability link is BROKEN.")
    ThemeObservabilityLogger = None

from edt_module_base import ModuleStatus
from ai_signal_adapter import AISignalAdapter
from signal_scorer import SignalScorer
from execution_adapter import ExecutionAdapter
from execution_modules import ExitManager, LiquidityChecker, PositionSizer, RiskGatekeeper


def _stable_trace_id(payload: Dict[str, Any], request_id: str | None) -> str:
    if request_id:
        return str(request_id)
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16].upper()
    return f"TRC-{digest}"


# Execution Layer Rating Priority (A=highest, D=lowest)
GRADE_RANK = {
    "A": 4,
    "B": 3,
    "C": 2,
    "D": 1,
}


class WorkflowRunner:
    """Main orchestration for execution-layer flow."""

    def __init__(
        self,
        config_path: str | None = None,
        execution_mode: str | None = None,
        audit_dir: str | None = None,
        request_store_path: str | None = None,
    ):
        self.config_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml"
        self.logs_dir = Path(audit_dir) if audit_dir else Path(__file__).resolve().parent.parent / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.request_store_path = Path(request_store_path) if request_store_path else self.logs_dir / "seen_request_ids.txt"
        self.request_store_path.parent.mkdir(parents=True, exist_ok=True)
        self._request_lock_path = self.request_store_path.with_suffix(self.request_store_path.suffix + ".lock")
        self._request_lock = threading.Lock()
        self._seen_request_ids = self._load_seen_request_ids()
        self._replay_log_path = self.logs_dir / "action_card_replay.jsonl"
        self._replay_lock = threading.Lock()
        self._replay_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

        self.scorer = SignalScorer()
        self.ai_adapter = AISignalAdapter(config_path=str(self.config_path))
        self.liquidity = LiquidityChecker()
        self.gatekeeper = RiskGatekeeper()
        self.sizer = PositionSizer()
        self.exit_mgr = ExitManager()
        mode = execution_mode or self._execution_mode_from_config()
        self.executor = ExecutionAdapter(mode=mode, audit_dir=str(self.logs_dir))

    def _execution_mode_from_config(self) -> str:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return str(cfg.get("modules", {}).get("ExecutionAdapter", {}).get("params", {}).get("mode", "dry_run"))
        except (OSError, yaml.YAMLError, TypeError, ValueError) as exc:
            logging.warning("Failed to read execution mode from config; fallback to dry_run: %s", exc)
            return "dry_run"

    def _risk_params_from_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return dict(cfg.get("modules", {}).get("RiskGatekeeper", {}).get("params", {}))
        except (OSError, yaml.YAMLError, TypeError, ValueError) as exc:
            logging.warning("Failed to read risk params from config; fallback to empty params: %s", exc)
            return {}

    def _theme_params_from_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return dict(cfg.get("modules", {}).get("ThemeCatalystEngine", {}).get("params", {}))
        except (OSError, yaml.YAMLError, TypeError, ValueError) as exc:
            logging.warning("Failed to read theme params from config; fallback to defaults: %s", exc)
            return {}

    def _safe_defaults(self, mode: str) -> Dict[str, Any]:
        params = self._risk_params_from_config()
        safe_cfg = params.get("ai_safe_defaults", {})
        if not safe_cfg or not bool(safe_cfg.get("enabled", False)):
            return {}
        if mode == "timeout":
            return dict(safe_cfg.get("on_ai_timeout", {}))
        if mode == "error":
            return dict(safe_cfg.get("on_ai_error", {}))
        return {}

    def _resolve_ai_factors(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve A0/A-1/A1/A1.5/A0.5 from AI output when present.
        Falls back to safe defaults on timeout/error.
        """
        base = {
            "A0": payload.get("A0", 0),
            "A-1": payload.get("A-1", 0),
            "A1": payload.get("A1", 0),
            "A1.5": payload.get("A1.5", 0),
            "A0.5": payload.get("A0.5", 0),
            "base_direction": payload.get("direction", "long"),
            "mapping_version": payload.get("mapping_version", "factor_map_v1"),
            "model_id": payload.get("model_id", "unknown"),
            "prompt_version": payload.get("prompt_version", "unknown"),
            "temperature": payload.get("temperature", 0.0),
            "timeout_ms": payload.get("timeout_ms", 10000),
            "ai_review_required": bool(payload.get("ai_review_required", False)),
            "ai_review_passed": bool(payload.get("ai_review_passed", True)),
            "ai_failure_mode": str(payload.get("ai_failure_mode", "none")).lower(),
            "narrative_state": payload.get("narrative_state"),
        }

        failure_mode = base["ai_failure_mode"]
        if failure_mode in {"timeout", "error"}:
            safe = self._safe_defaults(failure_mode)
            if safe:
                base.update(
                    {
                        "A0": safe.get("A0", base["A0"]),
                        "A-1": safe.get("A-1", base["A-1"]),
                        "A1": safe.get("A1", base["A1"]),
                        "A1.5": safe.get("A1.5", base["A1.5"]),
                        "A0.5": safe.get("A0.5", base["A0.5"]),
                        "base_direction": "neutral",
                        "ai_review_required": True,
                        "ai_review_passed": False,
                    }
                )
                return base

        ai_payload = payload.get("ai_intel_output")
        if not isinstance(ai_payload, dict):
            return base

        if "trace_id" not in ai_payload and payload.get("trace_id"):
            ai_payload["trace_id"] = payload.get("trace_id")
        if "event_id" not in ai_payload and payload.get("event_id"):
            ai_payload["event_id"] = payload.get("event_id")
        if payload.get("mapping_version"):
            ai_payload["mapping_version"] = payload.get("mapping_version")
        if payload.get("previous_narrative_state"):
            ai_payload["previous_narrative_state"] = payload.get("previous_narrative_state")

        mapped = self.ai_adapter.run(ai_payload)
        if mapped.status != ModuleStatus.SUCCESS:
            safe = self._safe_defaults("error")
            if safe:
                base.update(
                    {
                        "A0": safe.get("A0", 0),
                        "A-1": safe.get("A-1", 0),
                        "A1": safe.get("A1", 0),
                        "A1.5": safe.get("A1.5", 0),
                        "A0.5": safe.get("A0.5", 100),
                        "base_direction": "neutral",
                        "ai_failure_mode": "error",
                        "ai_review_required": True,
                        "ai_review_passed": False,
                    }
                )
                return base
            return base

        base.update(
            {
                "A0": mapped.data["A0"],
                "A-1": mapped.data["A-1"],
                "A1": mapped.data["A1"],
                "A1.5": mapped.data["A1.5"],
                "A0.5": mapped.data["A0.5"],
                "base_direction": mapped.data.get("base_direction", base["base_direction"]),
                "mapping_version": mapped.data.get("mapping_version", base["mapping_version"]),
                "model_id": mapped.data.get("model_id", base["model_id"]),
                "prompt_version": mapped.data.get("prompt_version", base["prompt_version"]),
                "temperature": mapped.data.get("temperature", base["temperature"]),
                "timeout_ms": mapped.data.get("timeout_ms", base["timeout_ms"]),
                "ai_review_required": bool(mapped.data.get("ai_review_required", base["ai_review_required"])),
                "ai_review_passed": bool(mapped.data.get("ai_review_passed", base["ai_review_passed"])),
                "narrative_state": mapped.data.get("narrative_state"),
            }
        )
        return base

    def _load_seen_request_ids(self) -> set[str]:
        ids: set[str] = set()
        with self._request_lock:
            with self._request_file_lock():
                if not self.request_store_path.exists():
                    return set()
                with open(self.request_store_path, "r", encoding="utf-8") as f:
                    for line in f:
                        req = line.strip()
                        if req:
                            ids.add(req)
        return ids

    def _persist_request_id(self, request_id: str) -> None:
        with open(self.request_store_path, "a", encoding="utf-8") as f:
            f.write(request_id + "\n")

    @contextmanager
    def _request_file_lock(self):
        lock_path = str(self._request_lock_path)
        self._request_lock_path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(200):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                time.sleep(0.01)
        else:
            raise TimeoutError(f"Could not acquire request-id lock: {lock_path}")

        try:
            yield
        finally:
            try:
                os.remove(lock_path)
            except FileNotFoundError:
                pass

    def _request_id_exists_on_disk(self, request_id: str) -> bool:
        if not self.request_store_path.exists():
            return False
        with open(self.request_store_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() == request_id:
                    return True
        return False

    def _is_request_processed(self, request_id: str | None) -> bool:
        if not request_id:
            return False
        with self._request_lock:
            if request_id in self._seen_request_ids:
                return True
            with self._request_file_lock():
                on_disk = self._request_id_exists_on_disk(request_id)
            if on_disk:
                self._seen_request_ids.add(request_id)
            return on_disk

    def _mark_request_processed(self, request_id: str | None) -> None:
        if not request_id:
            return
        with self._request_lock:
            with self._request_file_lock():
                if request_id in self._seen_request_ids or self._request_id_exists_on_disk(request_id):
                    self._seen_request_ids.add(request_id)
                    return
                self._persist_request_id(request_id)
                self._seen_request_ids.add(request_id)

    @staticmethod
    def _run_with_retry(module: Any, payload: Dict[str, Any], retries: int = 2) -> Any:
        out = module.run(payload)
        attempts = 0
        while out.status != ModuleStatus.SUCCESS and attempts < retries:
            attempts += 1
            out = module.run(payload)
        return out

    @staticmethod
    def _pack_step(step_name: str, module_output: Any) -> Dict[str, Any]:
        return {
            "step": step_name,
            "status": module_output.status.value,
            "data": module_output.data,
            "errors": module_output.errors,
            "warnings": module_output.warnings,
        }

    def _apply_theme_routing(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """A2.5 阶段融合主链宏观与主题副链信号"""
        macro_regime = payload.get("macro_regime")
        trade_grade = payload.get("trade_grade", "D")
        theme_params = self._theme_params_from_config()

        # 默认契约信息
        contract_cfg = theme_params.get("default_contract", {})

        theme_output = {
            "contract_name": "theme_catalyst_engine",
            "contract_version": contract_cfg.get("version", "v1.0"),
            "producer_module": contract_cfg.get("producer", "theme_engine"),
            "safe_to_consume": payload.get("safe_to_consume", False),
            "fallback_reason": payload.get("fallback_reason", "unknown_fallback"),
            "error_code": payload.get("error_code"),

            "primary_theme": payload.get("primary_theme", "unknown"),
            "current_state": payload.get("current_state", "DEAD"),
            "continuation_probability": payload.get("continuation_probability", 0.0),
            "trade_grade": trade_grade,
            "candidate_audit_pool": payload.get("candidate_audit_pool", []),

            "macro_regime": macro_regime,
            "macro_override_reason": payload.get("macro_override_reason", "none"),

            "conflict_flag": False,
            "conflict_type": "unknown_conflict",
            "final_decision_source": "theme_only",
            "theme_capped_by_macro": False,
            "final_trade_cap": payload.get("final_trade_cap", "STANDARD"),
        }

        # 核心主副链路由逻辑
        if macro_regime == "RISK_OFF":
            theme_output["conflict_flag"] = True
            theme_output["conflict_type"] = "C1_market_reject"

            # 对齐扁平化配置项
            max_grade_str = theme_params.get("max_grade_risk_off", "C").upper()
            max_val = GRADE_RANK.get(max_grade_str, 2)
            current_val = GRADE_RANK.get(str(trade_grade).upper(), 1)

            if current_val > max_val:
                theme_output["trade_grade"] = max_grade_str
                theme_output["theme_capped_by_macro"] = True
                theme_output["macro_override_reason"] = f"RISK_OFF 环境强制削减评级到 {max_grade_str}"
            else:
                theme_output["theme_capped_by_macro"] = False

            theme_output["final_trade_cap"] = theme_params.get("final_trade_cap_risk_off", "INTRADAY")
            theme_output["final_decision_source"] = "mainchain_capped_theme"

        elif macro_regime == "MIXED":
            theme_output["conflict_flag"] = False
            theme_output["conflict_type"] = "C2_market_neutral"
            theme_output["theme_capped_by_macro"] = False
            theme_output["final_decision_source"] = "theme_only"
            theme_output["final_trade_cap"] = "1_TO_2_DAYS"

        elif macro_regime is not None:
            # C3: 宏观顺风 (RISK_ON 或其他有效值)
            theme_output["conflict_flag"] = False
            theme_output["conflict_type"] = "C3_market_favorable"
            theme_output["theme_capped_by_macro"] = False
            theme_output["final_decision_source"] = "theme_only"
            theme_output["final_trade_cap"] = payload.get("final_trade_cap", "STANDARD")

        # 主链缺失时的一致性回退 (按规范 L87-L91)
        if macro_regime is None:
            missing_cfg = theme_params.get("missing_mainchain", {})
            theme_output["final_decision_source"] = "theme_only_degraded"
            theme_output["fallback_reason"] = "MAINCHAIN_MISSING"
            theme_output["safe_to_consume"] = False
            theme_output["theme_capped_by_macro"] = True
            theme_output["final_trade_cap"] = missing_cfg.get("action", "INTRADAY")

        return theme_output

    @staticmethod
    def _normalize_direction(raw_direction: Any) -> tuple[str, bool]:
        """
        Normalize analysis-layer directions for execution-layer compatibility.
        Supported upstream aliases:
        - flip_long  -> long
        - flip_short -> short
        """
        d = str(raw_direction or "long").strip().lower()
        if d in ("long", "short", "neutral"):
            return d, False
        if d == "flip_long":
            return "long", True
        if d == "flip_short":
            return "short", True
        return "neutral", False

    @staticmethod
    def _normalize_event_state(raw_state: Any) -> str:
        state = str(raw_state or "").strip().lower()
        mapping = {
            "initial": "Initial",
            "developing": "Developing",
            "peak": "Peak",
            "fading": "Fading",
            "dead": "Dead",
            "active": "Developing",
            "exhaustion": "Peak",
            "detected": "Initial",
        }
        return mapping.get(state, "Initial")

    @staticmethod
    def _derive_a1_market_validation(payload: Dict[str, Any], ai_factors: Dict[str, Any]) -> str:
        explicit = str(payload.get("a1_market_validation", "")).strip().lower()
        if explicit in {"pass", "partial", "fail"}:
            return explicit
        a1 = float(ai_factors.get("A1", payload.get("A1", 0)) or 0)
        if a1 >= 80:
            return "pass"
        if a1 >= 60:
            return "partial"
        return "fail"

    @staticmethod
    def _derive_trading_state(event_state: str, a1_validation: str) -> str:
        if a1_validation == "fail":
            return "avoid"
        if event_state == "Initial":
            return "probe" if a1_validation == "pass" else "observe"
        if event_state == "Developing":
            return "tradable" if a1_validation == "pass" else "probe"
        if event_state in {"Peak", "Fading"}:
            return "reduce" if a1_validation == "pass" else "avoid"
        return "avoid"

    @staticmethod
    def _derive_trading_state_with_market(
        event_state: str,
        a1_validation: str,
        macro_confirmation: str,
        sector_confirmation: str,
        leader_confirmation: str,
    ) -> str:
        if a1_validation == "fail":
            return "avoid"
        if event_state == "Initial":
            return "probe" if a1_validation == "pass" else "observe"
        if event_state == "Developing":
            if (
                a1_validation == "pass"
                and macro_confirmation == "supportive"
                and sector_confirmation == "strong"
                and leader_confirmation == "confirmed"
            ):
                return "addable"
            return "tradable" if a1_validation == "pass" else "probe"
        if event_state in {"Peak", "Fading"}:
            return "reduce" if a1_validation == "pass" else "avoid"
        return "avoid"

    @staticmethod
    def _derive_trade_grade(score: float) -> str:
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 45:
            return "C"
        return "D"

    @staticmethod
    def _derive_decision_and_position(event_state: str, trading_state: str, a1_validation: str) -> tuple[str, str]:
        if a1_validation == "fail" or event_state == "Dead":
            return "avoid", "none"
        if trading_state == "addable":
            return "overnight_allowed", "medium"
        if trading_state == "tradable":
            return "tradable", "medium"
        if trading_state == "probe":
            return "intraday_only", "test"
        if trading_state == "reduce":
            return "observe_only", "light"
        return "observe_only", "none"

    @staticmethod
    def _derive_time_window(payload: Dict[str, Any]) -> str:
        event_time = payload.get("event_time")
        if not event_time:
            return "0-24h"
        try:
            ts = str(event_time).replace("Z", "+00:00")
            start = datetime.fromisoformat(ts)
            now = datetime.now(timezone.utc)
            if not start.tzinfo:
                start = start.replace(tzinfo=timezone.utc)
            hours = (now - start.astimezone(timezone.utc)).total_seconds() / 3600.0
        except Exception:
            return "0-24h"
        if hours <= 24:
            return "0-24h"
        if hours <= 48:
            return "24-48h"
        if hours <= 72:
            return "48-72h"
        if hours <= 120:
            return "72-120h"
        return ">120h"

    @staticmethod
    def _derive_execution_window(decision: str, trading_state: str, event_state: str) -> str:
        if decision == "intraday_only":
            return "intraday"
        if decision == "avoid":
            return "next_day_watch"
        if trading_state == "reduce" or event_state in {"Peak", "Fading"}:
            return "close_near"
        return "open"

    @staticmethod
    def _resolve_target(payload: Dict[str, Any]) -> tuple[str, str]:
        def _normalize_list(value: Any) -> list[str]:
            if isinstance(value, list):
                return [str(x).strip() for x in value if str(x).strip()]
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []

        leaders = _normalize_list(payload.get("target_leader"))
        etf = _normalize_list(payload.get("target_etf"))
        sectors = _normalize_list(payload.get("target_sector"))
        followers = _normalize_list(payload.get("target_followers"))
        if leaders:
            return "Leader", leaders[0]
        if etf:
            return "ETF", etf[0]
        if sectors:
            return "Sector", sectors[0]
        if followers:
            return "Follower", followers[0]
        symbol = str(payload.get("symbol", "")).strip()
        if symbol:
            return "Leader", symbol
        return "Follower", "N/A"

    @staticmethod
    def _normalize_event_type(raw_type: Any) -> str:
        allowed = {
            "tariff",
            "geo_political",
            "earnings",
            "monetary",
            "energy",
            "shipping",
            "industrial",
            "tech",
            "healthcare",
            "regulatory",
            "merger",
            "inflation",
            "commodity",
            "credit",
            "natural_disaster",
            "pandemic",
            "other",
        }
        event_type = str(raw_type or "").strip().lower()
        return event_type if event_type in allowed else "other"

    @staticmethod
    def _is_true(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _evaluate_output_gate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        blockers: list[str] = []

        # Only enforce "missing opportunity" when upstream explicitly provides this field.
        if "has_opportunity" in payload and not self._is_true(payload.get("has_opportunity")):
            blockers.append("missing_opportunity")

        # Explicit tradeability has highest priority.
        if "tradeable" in payload and not self._is_true(payload.get("tradeable")):
            blockers.append("tradeable_false")

        if "market_data_present" in payload and not self._is_true(payload.get("market_data_present")):
            blockers.append("market_data_missing")
        if "market_data_stale" in payload and self._is_true(payload.get("market_data_stale")):
            blockers.append("market_data_stale")
        if "market_data_default_used" in payload and self._is_true(payload.get("market_data_default_used")):
            blockers.append("market_data_default_used")
        if "market_data_fallback_used" in payload and self._is_true(payload.get("market_data_fallback_used")):
            blockers.append("market_data_fallback_used")

        if not blockers:
            return {"blocked": False, "action": "ALLOW", "blockers": [], "reason": ""}

        action = "BLOCK" if "tradeable_false" in blockers else "WATCH"
        return {
            "blocked": True,
            "action": action,
            "blockers": blockers,
            "reason": ";".join(blockers),
        }

    def _log_replay_task(
        self,
        *,
        trace_id: str,
        request_id: str | None,
        batch_id: str | None,
        final_action: str,
        payload: Dict[str, Any],
        action_card: Dict[str, Any],
    ) -> None:
        record = {
            "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "final_action": final_action,
            "event_id": payload.get("event_id"),
            "action_card": action_card,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._replay_lock:
            with open(self._replay_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _submit_replay_log(
        self,
        *,
        trace_id: str,
        request_id: str | None,
        batch_id: str | None,
        final_action: str,
        payload: Dict[str, Any],
        action_card: Dict[str, Any],
    ) -> None:
        try:
            self._replay_executor.submit(
                self._log_replay_task,
                trace_id=trace_id,
                request_id=request_id,
                batch_id=batch_id,
                final_action=final_action,
                payload=payload,
                action_card=action_card,
            )
        except Exception as exc:
            logging.warning("replay_log_submit_failed: %s", exc)

    def _build_action_card(
        self,
        payload: Dict[str, Any],
        ai_factors: Dict[str, Any],
        score: float,
        final_action: str,
    ) -> Dict[str, Any]:
        event_state = self._normalize_event_state(payload.get("event_state"))
        a1_validation = self._derive_a1_market_validation(payload, ai_factors)
        macro_confirmation = str(payload.get("macro_confirmation", "")).strip().lower()
        sector_confirmation = str(payload.get("sector_confirmation", "")).strip().lower()
        leader_confirmation = str(payload.get("leader_confirmation", "")).strip().lower()
        if not macro_confirmation:
            macro_state = str(payload.get("macro_state", "")).strip().lower()
            if macro_state == "risk-on":
                macro_confirmation = "supportive"
            elif macro_state == "risk-off":
                macro_confirmation = "hostile"
            else:
                macro_confirmation = "neutral"
        trading_state = self._derive_trading_state_with_market(
            event_state,
            a1_validation,
            macro_confirmation,
            sector_confirmation,
            leader_confirmation,
        )
        decision, position = self._derive_decision_and_position(event_state, trading_state, a1_validation)
        grade = self._derive_trade_grade(score)
        if decision == "avoid":
            grade = "D"
        evidence_grade = str(payload.get("evidence_grade", "C")).strip().upper()
        if evidence_grade == "C" and decision in {"tradable", "overnight_allowed"}:
            decision = "observe_only"
            position = "none"
            trading_state = "observe"
            grade = "C"

        best_setup = "pullback_confirm"
        if decision == "avoid":
            best_setup = "avoid"
        elif event_state in {"Peak", "Fading"}:
            best_setup = "no_chase"
        elif event_state == "Initial":
            best_setup = "breakout"

        blockers = []
        if a1_validation == "fail":
            blockers.append("A1 market validation fail")
        if evidence_grade == "C":
            blockers.append("Evidence grade C: no tradable/overnight")
        if event_state == "Dead":
            blockers.append("Catalyst state is dead")
        if final_action in {"BLOCK", "FORCE_CLOSE"}:
            blockers.append(f"execution_gate_{final_action.lower()}")
        elif final_action == "WATCH":
            blockers.append("execution_gate_watch")

        # Final-action hard convergence to avoid contract conflicts with orchestrator output.
        if final_action in {"BLOCK", "FORCE_CLOSE"}:
            trading_state = "avoid"
            decision = "avoid"
            position = "none"
            grade = "D"
            best_setup = "avoid"
        elif final_action == "WATCH":
            if decision in {"tradable", "overnight_allowed", "intraday_only"}:
                trading_state = "observe"
                decision = "observe_only"
                position = "none"
                if grade == "A" or grade == "B":
                    grade = "C"

        catalyst_state = {
            "Initial": "First Impulse",
            "Developing": "Continuation",
            "Peak": "Exhaustion",
            "Fading": "Exhaustion",
            "Dead": "Dead",
        }[event_state]
        macro_state = str(payload.get("macro_state", "mixed"))
        if macro_state not in {"risk-on", "mixed", "risk-off"}:
            macro_state = "risk-off" if a1_validation == "fail" else "mixed"
        target_bucket, resolved_target = self._resolve_target(payload)

        return {
            "event_name": str(payload.get("event_name") or payload.get("headline") or payload.get("event_id", "")),
            "event_type": self._normalize_event_type(payload.get("event_type", "other")),
            "event_time": str(payload.get("event_time") or payload.get("timestamp") or ""),
            "time_window": self._derive_time_window(payload),
            "evidence_grade": evidence_grade,
            "catalyst_state": catalyst_state,
            "primary_path": str(payload.get("primary_path", "undetermined")),
            "secondary_paths": list(payload.get("secondary_paths", [])),
            "rejected_paths": list(payload.get("rejected_paths", [])),
            "target_bucket": target_bucket,
            "macro_state": macro_state,
            "sector_confirmation": sector_confirmation or "weak",
            "leader_confirmation": leader_confirmation or "unconfirmed",
            "a1_market_validation": a1_validation,
            "trading_state": trading_state,
            "trade_grade": grade,
            "trade_decision": decision,
            "best_target": resolved_target,
            "best_setup": best_setup,
            "position_tier": position,
            "execution_window": self._derive_execution_window(decision, trading_state, event_state),
            "risk_switches": list(payload.get("risk_switches", [])),
            "invalidators": list(payload.get("invalidators", ["Primary path invalidated"])),
            "downgrade_rules": list(payload.get("downgrade_rules", ["A1 downgrade"])),
            "blockers": blockers,
            "one_line_verdict": f"[{grade}][{decision}] {payload.get('symbol', 'N/A')}",
            "event_state": event_state,
        }

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = payload.get("request_id")
        trace_id = _stable_trace_id(payload, request_id)
        batch_id = payload.get("batch_id")
        result: Dict[str, Any] = {
            "input": payload,
            "steps": [],
            "trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
        }
        contract_version = str(payload.get("contract_version", "v2.2"))
        legacy_contract_version = str(payload.get("legacy_contract_version", "v1.0"))
        result["contract"] = {
            "contract_version": contract_version,
            "legacy_contract_version": legacy_contract_version,
            "dual_write": bool(payload.get("dual_write", True)),
        }
        if self._is_request_processed(request_id):
            result["final"] = {
                "action": "DUPLICATE_IGNORED",
                "reason": f"request_id={request_id} already processed",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "contract_version": contract_version,
            }
            return result

        start_time = time.time()
        ai_factors = self._resolve_ai_factors(payload)
        score_in = {
            "event_id": payload.get("event_id", f"EXEC-{payload.get('request_id', 'NA')}"),
            "severity": payload.get("severity", "E3"),
            "A0": ai_factors["A0"],
            "A-1": ai_factors["A-1"],
            "A1": ai_factors["A1"],
            "A1.5": ai_factors["A1.5"],
            "A0.5": ai_factors["A0.5"],
            "fatigue_final": payload.get("fatigue_index", 0),
            "a_minus_1_discount_factor": payload.get("a_minus_1_discount_factor", 1.0),
            "correlation": payload.get("correlation", 0.5),
            "is_crowded": payload.get("is_crowded", False),
            "narrative_mode": payload.get("narrative_mode", "Fact-Driven"),
            "policy_intervention": payload.get("policy_intervention", "NONE"),
            "base_direction": ai_factors["base_direction"],
            "watch_mode": payload.get("watch_mode", False),
            "weights_version": payload.get("weights_version", "score_v1"),
        }
        score_out = self._run_with_retry(self.scorer, score_in)
        result["steps"].append(self._pack_step("signal", score_out))
        if score_out.status != ModuleStatus.SUCCESS:
            result["final"] = {
                "action": "ERROR",
                "reason": "SignalScorer failed",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
            }
            return result
        result["signal"] = score_out.data
        score = score_out.data["score"]
        action_card = self._build_action_card(payload, ai_factors, float(score), "PENDING")

        liq_in = {
            "vix": payload.get("vix", 18),
            "ted": payload.get("ted", 40),
            "correlation": payload.get("correlation", 0.5),
            "spread_pct": payload.get("spread_pct", 0.002),
        }
        liq_out = self._run_with_retry(self.liquidity, liq_in)
        result["steps"].append(self._pack_step("liquidity", liq_out))
        if liq_out.status != ModuleStatus.SUCCESS:
            result["final"] = {
                "action": "ERROR",
                "reason": "LiquidityChecker failed",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
            }
            result["action_card"] = action_card
            return result
        result["liquidity"] = liq_out.data

        gate_in = {
            "event_state": payload.get("event_state", "Active"),
            "fatigue_index": payload.get("fatigue_index", 0),
            "liquidity_state": liq_out.data["liquidity_state"],
            "spread_multiplier": liq_out.data["spread_multiplier"],
            "correlation": payload.get("correlation", 0.5),
            "score": score,
            "severity": payload.get("severity", "E3"),
            "A1": ai_factors["A1"],
            "policy_intervention": payload.get("policy_intervention", "NONE"),
            "ai_failure_mode": ai_factors.get("ai_failure_mode", "none"),
            "ai_review_required": ai_factors.get("ai_review_required", False),
            "ai_review_passed": ai_factors.get("ai_review_passed", True),
            "mapping_version": ai_factors.get("mapping_version", "factor_map_v1"),
            "model_id": ai_factors.get("model_id", "unknown"),
            "prompt_version": ai_factors.get("prompt_version", "unknown"),
            "temperature": ai_factors.get("temperature", 0.0),
            "timeout_ms": ai_factors.get("timeout_ms", 10000),
        }
        gate_out = self._run_with_retry(self.gatekeeper, gate_in)
        result["steps"].append(self._pack_step("risk", gate_out))
        if gate_out.status != ModuleStatus.SUCCESS:
            result["final"] = {
                "action": "ERROR",
                "reason": "RiskGatekeeper failed",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
            }
            result["action_card"] = action_card
            return result
        result["risk"] = gate_out.data

        # ================= A2.5 主题副链路由拦截 =================
        if payload.get("event_scope") == "sector_theme" and payload.get("contract_name") == "theme_catalyst_engine":
            theme_output = self._apply_theme_routing(payload)
            macro_regime = theme_output.get("macro_regime")
            safe_to_consume = theme_output.get("safe_to_consume", False)
            latency_ms = int((time.time() - start_time) * 1000)

            # 主链优先: RISK_OFF 绝对拦截
            if macro_regime == "RISK_OFF":
                if ThemeObservabilityLogger:
                    ThemeObservabilityLogger.log_observability_event(theme_output, trace_id, "blocked", latency_ms)
                result["final"] = {
                    "action": "BLOCK",
                    "reason": "RISK_OFF 环境拦截，主链优先给上限",
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "batch_id": batch_id,
                }
                result["action_card"] = self._build_action_card(payload, ai_factors, float(score), "BLOCK")
                self._submit_replay_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    batch_id=batch_id,
                    final_action="BLOCK",
                    payload=payload,
                    action_card=result["action_card"],
                )
                result["theme_output"] = theme_output
                self._mark_request_processed(request_id)
                return result

            # 副链调整: safe_to_consume == True 正常处理
            elif safe_to_consume:
                if ThemeObservabilityLogger:
                    ThemeObservabilityLogger.log_observability_event(theme_output, trace_id, "success", latency_ms)
                result["theme_output"] = theme_output

            # 副链异常: 降级 WATCH
            else:
                if ThemeObservabilityLogger:
                    ThemeObservabilityLogger.log_observability_event(theme_output, trace_id, "degraded", latency_ms)
                result["final"] = {
                    "action": "WATCH",
                    "reason": f"Theme subchain degraded: {theme_output['fallback_reason']}",
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "batch_id": batch_id,
                }
                result["action_card"] = self._build_action_card(payload, ai_factors, float(score), "WATCH")
                self._submit_replay_log(
                    trace_id=trace_id,
                    request_id=request_id,
                    batch_id=batch_id,
                    final_action="WATCH",
                    payload=payload,
                    action_card=result["action_card"],
                )
                result["theme_output"] = theme_output
                self._mark_request_processed(request_id)
                return result
        # ================= A2.5 阶段结束 =================

        output_gate = self._evaluate_output_gate(payload)
        result["output_gate"] = output_gate

        forced_action = str(gate_out.data.get("final_action", "EXECUTE"))
        forced_reason = "Blocked by gates or no valid position."
        if output_gate.get("blocked") and forced_action not in ("BLOCK", "FORCE_CLOSE", "WATCH"):
            forced_action = str(output_gate.get("action", "WATCH"))
            forced_reason = f"Blocked by output gate: {output_gate.get('reason', 'unknown')}"

        if forced_action in ("BLOCK", "FORCE_CLOSE", "WATCH"):
            result["final"] = {
                "action": forced_action,
                "reason": forced_reason,
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "contract_version": contract_version,
            }
            result["action_card"] = self._build_action_card(payload, ai_factors, float(score), forced_action)
            self._submit_replay_log(
                trace_id=trace_id,
                request_id=request_id,
                batch_id=batch_id,
                final_action=forced_action,
                payload=payload,
                action_card=result["action_card"],
            )
            self._mark_request_processed(request_id)
            return result

        # Human confirmation node (T5.3)
        require_human_confirm = bool(payload.get("require_human_confirm", False)) or bool(
            gate_out.data.get("human_confirm_required", False)
        )
        human_confirmed = bool(payload.get("human_confirmed", False))
        if require_human_confirm and not human_confirmed:
            result["final"] = {
                "action": "PENDING_CONFIRM",
                "reason": "Human confirmation required before execution.",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "contract_version": contract_version,
            }
            result["human_confirm"] = {
                "required": True,
                "confirmed": False,
            }
            result["action_card"] = self._build_action_card(payload, ai_factors, float(score), "PENDING_CONFIRM")
            self._submit_replay_log(
                trace_id=trace_id,
                request_id=request_id,
                batch_id=batch_id,
                final_action="PENDING_CONFIRM",
                payload=payload,
                action_card=result["action_card"],
            )
            return result

        target_bucket, resolved_target = self._resolve_target(payload)
        enforce_resolved_symbol = self._is_true(payload.get("enforce_resolved_symbol", False))
        symbol_from_payload = str(payload.get("symbol", "")).strip()
        resolved_symbol = symbol_from_payload or (resolved_target if target_bucket != "Sector" else "")
        if not resolved_symbol:
            resolved_symbol = "UNKNOWN"

        if enforce_resolved_symbol and (resolved_symbol in {"UNKNOWN", "N/A", ""} or target_bucket == "Sector"):
            result["final"] = {
                "action": "WATCH",
                "reason": "Blocked by output gate: missing_tradeable_symbol",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "contract_version": contract_version,
            }
            result["action_card"] = self._build_action_card(payload, ai_factors, float(score), "WATCH")
            self._submit_replay_log(
                trace_id=trace_id,
                request_id=request_id,
                batch_id=batch_id,
                final_action="WATCH",
                payload=payload,
                action_card=result["action_card"],
            )
            self._mark_request_processed(request_id)
            return result

        size_in = {
            "score": score,
            "liquidity_state": liq_out.data["liquidity_state"],
            "risk_gate_multiplier": gate_out.data["position_multiplier"],
            "account_equity": payload.get("account_equity", 100000),
        }
        size_out = self._run_with_retry(self.sizer, size_in)
        result["steps"].append(self._pack_step("position", size_out))
        if size_out.status != ModuleStatus.SUCCESS:
            result["final"] = {
                "action": "ERROR",
                "reason": "PositionSizer failed",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
            }
            result["action_card"] = action_card
            return result
        result["position"] = size_out.data

        if float(size_out.data.get("final_notional", 0.0)) <= 0:
            result["final"] = {
                "action": "WATCH",
                "reason": "Final position notional is 0 after risk/position checks.",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "contract_version": contract_version,
            }
            result["action_card"] = self._build_action_card(payload, ai_factors, float(score), "WATCH")
            self._submit_replay_log(
                trace_id=trace_id,
                request_id=request_id,
                batch_id=batch_id,
                final_action="WATCH",
                payload=payload,
                action_card=result["action_card"],
            )
            self._mark_request_processed(request_id)
            return result

        normalized_direction, direction_was_normalized = self._normalize_direction(payload.get("direction", "long"))
        exit_in = {
            "entry_price": payload.get("entry_price", 100.0),
            "risk_per_share": payload.get("risk_per_share", 2.0),
            "direction": normalized_direction,
            "hold_days": payload.get("hold_days", 0),
            "profit_r": payload.get("profit_r", 0.0),
            "profit_retrace": payload.get("profit_retrace", 0.0),
        }
        exit_out = self._run_with_retry(self.exit_mgr, exit_in)
        result["steps"].append(self._pack_step("exit_plan", exit_out))
        if exit_out.status != ModuleStatus.SUCCESS:
            result["final"] = {
                "action": "ERROR",
                "reason": "ExitManager failed",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
            }
            result["action_card"] = action_card
            return result
        result["exit_plan"] = exit_out.data

        # Build execution order and pass to adapter (dry-run by default).
        order = {
            "action": "OPEN_LONG" if normalized_direction == "long" else "OPEN_SHORT",
            "symbol": resolved_symbol,
            "notional": size_out.data["final_notional"],
            "entry_price": payload.get("entry_price", 100.0),
            "stop_loss": exit_out.data["hard_stop"],
            "take_profit_levels": exit_out.data["take_profit_levels"],
            "request_id": request_id,
            "trace_id": trace_id,
            "batch_id": payload.get("batch_id"),
        }
        execution_receipt = self.executor.execute(order)

        result["final"] = {
            "action": "EXECUTE",
            "score": score,
            "position_pct": size_out.data["final_position_pct"],
            "position_notional": size_out.data["final_notional"],
            "liquidity_state": liq_out.data["liquidity_state"],
            "execution_ticket": execution_receipt["ticket_id"],
            "execution_mode": execution_receipt["mode"],
            "trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "contract_version": contract_version,
        }
        result["human_confirm"] = {
            "required": require_human_confirm,
            "confirmed": human_confirmed,
        }
        result["direction"] = {
            "raw": payload.get("direction", "long"),
            "normalized": normalized_direction,
            "normalized_from_flip": direction_was_normalized,
        }
        result["execution_receipt"] = execution_receipt
        result["action_card"] = self._build_action_card(payload, ai_factors, float(score), "EXECUTE")
        self._submit_replay_log(
            trace_id=trace_id,
            request_id=request_id,
            batch_id=batch_id,
            final_action="EXECUTE",
            payload=payload,
            action_card=result["action_card"],
        )
        result["ai_factors"] = {
            "A0": ai_factors["A0"],
            "A-1": ai_factors["A-1"],
            "A1": ai_factors["A1"],
            "A1.5": ai_factors["A1.5"],
            "A0.5": ai_factors["A0.5"],
            "mapping_version": ai_factors.get("mapping_version", "factor_map_v1"),
            "narrative_state": ai_factors.get("narrative_state"),
        }
        result["batch_id"] = batch_id
        self._mark_request_processed(request_id)
        return result


if __name__ == "__main__":
    runner = WorkflowRunner()
    sample = {
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.55,
        "vix": 19,
        "ted": 45,
        "spread_pct": 0.003,
        "account_equity": 150000,
        "entry_price": 42.5,
        "risk_per_share": 1.5,
        "direction": "long",

        # Theme Catalyst integration fields
        "event_scope": "sector_theme",
        "contract_name": "theme_catalyst_engine",
        "macro_regime": None,
        "trade_grade": "A",
        "safe_to_consume": True,
        "primary_theme": "AI_Infrastructure",
    }
    out = runner.run(sample)
    print(json.dumps(out, indent=2, ensure_ascii=False))
