#!/usr/bin/env python3
"""
Orchestrator module for AI node orchestration (C2).
- Input/output specification
- Retry with exponential backoff
- Timeout handling
- Circuit breaker
- Fallback degradation
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import atexit

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_trace_id(node_type: str, payload: Dict[str, Any]) -> str:
    canonical = json.dumps({"node_type": node_type, "payload": payload}, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16].upper()
    return f"TRC-{digest}"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout_ms: int = 60000
    _failures: int = 0
    _state: str = "CLOSED"
    _last_failure_time: float = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = "CLOSED"

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self.failure_threshold:
                self._state = "OPEN"

    def can_execute(self) -> bool:
        with self._lock:
            if self._state == "CLOSED":
                return True
            if self._state == "OPEN":
                elapsed = (time.time() - self._last_failure_time) * 1000
                if elapsed >= self.recovery_timeout_ms:
                    self._state = "HALF_OPEN"
                    return True
                return False
            return True

    @property
    def state(self) -> str:
        with self._lock:
            return self._state


class OrchestratorNode(EDTModule):
    node_type: str = "orchestrator"
    schema_version: str = "1.0.0"

    def __init__(self, config_path: str | None = None):
        resolved_config = config_path or _default_config_path()
        super().__init__("OrchestratorNode", "1.0.0", resolved_config)
        self.config_path = Path(resolved_config)
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)
        atexit.register(self._executor.shutdown, wait=False)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if "node_type" not in input_data:
            return False, "node_type is required"
        if "payload" not in input_data:
            return False, "payload is required"
        return True, None

    def _get_circuit_breaker(self, node_type: str, override_config: Dict[str, Any]) -> CircuitBreaker:
        with self._lock:
            if node_type not in self._circuit_breakers:
                cfg = self._get_config("modules.OrchestratorNode.params.circuit_breaker", {})
                failure_threshold = int(override_config.get("failure_threshold", cfg.get("failure_threshold", 5)))
                recovery_timeout_ms = int(override_config.get("recovery_timeout_ms", cfg.get("recovery_timeout_ms", 60000)))
                self._circuit_breakers[node_type] = CircuitBreaker(
                    failure_threshold=failure_threshold,
                    recovery_timeout_ms=recovery_timeout_ms,
                )
            return self._circuit_breakers[node_type]

    def _execute_with_timeout(self, module: EDTModule, payload: Dict[str, Any], timeout_ms: int) -> ModuleOutput:
        future = self._executor.submit(module.run, payload)
        try:
            return future.result(timeout=timeout_ms / 1000)
        except FutureTimeoutError:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "TIMEOUT", "message": f"Execution timeout after {timeout_ms}ms"}],
            )

    def _execute_with_retry(
        self,
        node_type: str,
        payload: Dict[str, Any],
        retry_config: Dict[str, Any],
        timeout_ms: int,
    ) -> tuple[Optional[Dict[str, Any]], str, int]:
        cfg = self._get_config("modules.OrchestratorNode.params.retry", {})
        max_attempts = int(retry_config.get("max_attempts", cfg.get("max_attempts", 3)))
        backoff_factor = float(retry_config.get("backoff_factor", cfg.get("backoff_factor", 2.0)))
        retry_on = set(retry_config.get("retry_on", cfg.get("retry_on", ["TIMEOUT", "NETWORK_ERROR"])))

        module = self._get_module(node_type)
        if not module:
            return None, f"Module {node_type} not found", 0

        for attempt in range(1, max_attempts + 1):
            result = self._execute_with_timeout(module, payload, timeout_ms)
            if result.status == ModuleStatus.SUCCESS:
                return result.data, "", attempt

            error_code = result.errors[0].get("code", "UNKNOWN") if result.errors else "UNKNOWN"
            if error_code not in retry_on:
                return None, f"Non-retryable error: {error_code}", attempt

            if attempt < max_attempts:
                sleep_time = max(0.0, backoff_factor ** (attempt - 1))
                time.sleep(sleep_time)

        return None, f"Failed after {max_attempts} attempts", max_attempts

    def _get_module(self, node_type: str) -> Optional[EDTModule]:
        if node_type == "ai_event_intel":
            from ai_event_intel import EventEvidenceScorer

            return EventEvidenceScorer(config_path=str(self.config_path))
        if node_type == "signal_scorer":
            from signal_scorer import SignalScorer

            return SignalScorer(config_path=str(self.config_path))
        if node_type == "risk_gatekeeper":
            from execution_modules import RiskGatekeeper

            return RiskGatekeeper(config_path=str(self.config_path))
        return None

    def _apply_fallback(self, node_type: str, fallback_config: Dict[str, Any], error: str) -> Dict[str, Any]:
        default_cfg = self._get_config("modules.OrchestratorNode.params.fallback", {})
        enabled = bool(fallback_config.get("enabled", default_cfg.get("enabled", True)))
        default_action = fallback_config.get("default_action", default_cfg.get("default_action", "WATCH"))

        if not enabled:
            return {"action": default_action, "node_type": node_type, "fallback_used": False}

        return {
            "action": default_action,
            "fallback_reason": error,
            "node_type": node_type,
            "fallback_used": True,
            "generated_at": _now_iso(),
        }

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        start_time = time.time()
        data = input_data.raw_data

        node_type = data.get("node_type")
        payload = data.get("payload", {})
        trace_id = data.get("trace_id") or _stable_trace_id(str(node_type), payload)

        default_timeout = int(self._get_config("modules.OrchestratorNode.params.timeout_ms", 10000))
        timeout_ms = int(data.get("timeout_ms", default_timeout))
        retry_config = data.get("retry", {})
        circuit_config = data.get("circuit_breaker", {})
        fallback_config = data.get("fallback", {})

        cb = self._get_circuit_breaker(node_type, circuit_config)
        if not cb.can_execute():
            fallback_data = self._apply_fallback(node_type, fallback_config, "Circuit breaker open")
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data={
                    "trace_id": trace_id,
                    "node_type": node_type,
                    "status": "CIRCUIT_OPEN",
                    "data": fallback_data,
                    "attempts": 0,
                    "circuit_state": cb.state,
                    "fallback_used": True,
                    "execution_time_ms": int((time.time() - start_time) * 1000),
                },
                warnings=["CIRCUIT_OPEN: fallback returned"],
            )

        result_data, error, attempts = self._execute_with_retry(node_type, payload, retry_config, timeout_ms)

        if error:
            cb.record_failure()
            fallback_data = self._apply_fallback(node_type, fallback_config, error)
            status = "TIMEOUT" if "timeout" in error.lower() else "FAILED"
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data={
                    "trace_id": trace_id,
                    "node_type": node_type,
                    "status": "FALLBACK",
                    "data": fallback_data,
                    "attempts": attempts,
                    "circuit_state": cb.state,
                    "fallback_used": True,
                    "execution_time_ms": int((time.time() - start_time) * 1000),
                },
                errors=[{"code": status, "message": error}],
                warnings=["FALLBACK_USED"],
            )

        cb.record_success()
        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "trace_id": trace_id,
                "node_type": node_type,
                "status": "SUCCESS",
                "data": result_data,
                "attempts": attempts,
                "circuit_state": cb.state,
                "fallback_used": False,
                "execution_time_ms": int((time.time() - start_time) * 1000),
            },
        )


if __name__ == "__main__":
    test_input = {
        "trace_id": "TEST-001",
        "node_type": "ai_event_intel",
        "payload": {"headline": "Test news", "source_url": "https://example.com", "timestamp": _now_iso()},
        "retry": {"max_attempts": 2},
        "timeout_ms": 5000,
    }
    module = OrchestratorNode()
    result = module.run(test_input)
    print(f"Status: {result.status}")
    print(f"Data: {result.data}")
    print(f"Errors: {result.errors}")
