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
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
try:
    from logging.theme_observability import ThemeObservabilityLogger
except ImportError:
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
            "conflict_type": "none",
            "final_decision_source": "theme_only",
            "theme_capped_by_macro": False,
            "final_trade_cap": "STANDARD",
        }

        # 核心主副链路由逻辑
        if macro_regime == "RISK_OFF":
            theme_output["conflict_flag"] = True
            theme_output["conflict_type"] = "C1_market_reject"
            
            # 从配置获取上限评级
            risk_off_cfg = theme_params.get("risk_off", {})
            max_grade_str = risk_off_cfg.get("max_grade", "C").upper()
            max_val = GRADE_RANK.get(max_grade_str, 2)
            current_val = GRADE_RANK.get(str(trade_grade).upper(), 1)
            
            # 策略：如果不幸当前的评级(如A)高于上限(如C)，执行强制削减
            if current_val > max_val:
                theme_output["trade_grade"] = max_grade_str
                theme_output["theme_capped_by_macro"] = True
                theme_output["macro_override_reason"] = f"RISK_OFF 环境强制削减评级到 {max_grade_str}"
            else:
                theme_output["theme_capped_by_macro"] = False

            theme_output["final_trade_cap"] = risk_off_cfg.get("final_trade_cap", "INTRADAY")
            theme_output["final_decision_source"] = "mainchain_capped_theme"

        elif macro_regime == "MIXED":
            theme_output["conflict_flag"] = False
            theme_output["conflict_type"] = "C2_market_neutral"
            theme_output["theme_capped_by_macro"] = False
            theme_output["final_decision_source"] = "theme_only"

        elif macro_regime is not None:
            # C3: 宏观顺风 (RISK_ON 或其他有效值)
            theme_output["conflict_flag"] = False
            theme_output["conflict_type"] = "C3_market_favorable"
            theme_output["theme_capped_by_macro"] = False
            theme_output["final_decision_source"] = "theme_only"

        # 主链缺失时的一致性回退
        if macro_regime is None:
            missing_cfg = theme_params.get("missing_mainchain", {})
            theme_output["conflict_flag"] = True
            theme_output["conflict_type"] = "C4_mainchain_lost"
            theme_output["final_decision_source"] = "theme_only_degraded"
            theme_output["fallback_reason"] = "MAINCHAIN_MISSING"
            theme_output["safe_to_consume"] = False
            theme_output["theme_capped_by_macro"] = True
            theme_output["final_trade_cap"] = missing_cfg.get("action", "WATCH_ONLY")
            
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
        if self._is_request_processed(request_id):
            result["final"] = {
                "action": "DUPLICATE_IGNORED",
                "reason": f"request_id={request_id} already processed",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
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
                result["theme_output"] = theme_output
                self._mark_request_processed(request_id)
                return result
        # ================= A2.5 阶段结束 =================

        if gate_out.data["final_action"] in ("BLOCK", "FORCE_CLOSE", "WATCH"):
            result["final"] = {
                "action": gate_out.data["final_action"],
                "reason": "Blocked by gates or no valid position.",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
            }
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
            }
            result["human_confirm"] = {
                "required": True,
                "confirmed": False,
            }
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
            return result
        result["position"] = size_out.data

        if float(size_out.data.get("final_notional", 0.0)) <= 0:
            result["final"] = {
                "action": "WATCH",
                "reason": "Final position notional is 0 after risk/position checks.",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
            }
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
            return result
        result["exit_plan"] = exit_out.data

        # Build execution order and pass to adapter (dry-run by default).
        order = {
            "action": "OPEN_LONG" if normalized_direction == "long" else "OPEN_SHORT",
            "symbol": payload.get("symbol", "UNKNOWN"),
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
