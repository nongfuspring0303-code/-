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

import json
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import yaml

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        self.config_path = Path(config_path) if config_path else _default_config_path()
        self._config = self._load_config()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _get_config(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        val = self._config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def _get_circuit_breaker(self, node_type: str, config: Dict[str, Any]) -> CircuitBreaker:
        with self._lock:
            if node_type not in self._circuit_breakers:
                cb_config = config.get("circuit_breaker", {})
                self._circuit_breakers[node_type] = CircuitBreaker(
                    failure_threshold=cb_config.get("failure_threshold", 5),
                    recovery_timeout_ms=cb_config.get("recovery_timeout_ms", 60000),
                )
            return self._circuit_breakers[node_type]

    def _execute_with_retry(
        self,
        node_type: str,
        payload: Dict[str, Any],
        retry_config: Dict[str, Any],
        timeout_ms: int,
    ) -> tuple[Optional[Dict[str, Any]], str, int]:
        max_attempts = retry_config.get("max_attempts", 3)
        backoff_factor = retry_config.get("backoff_factor", 2.0)
        retry_on = set(retry_config.get("retry_on", ["TIMEOUT", "NETWORK_ERROR"]))

        module = self._get_module(node_type)
        if not module:
            return None, f"Module {node_type} not found", 0

        errors = []
        for attempt in range(1, max_attempts + 1):
            try:
                start_time = time.time()
                result = self._execute_with_timeout(module, payload, timeout_ms)
                elapsed_ms = int((time.time() - start_time) * 1000)
                if result.status == ModuleStatus.SUCCESS:
                    return result.data, "", attempt
                error_code = result.errors[0].get("code", "UNKNOWN") if result.errors else "UNKNOWN"
                if error_code not in retry_on:
                    return None, f"Non-retryable error: {error_code}", attempt
                errors.append(result.errors)
            except Exception as e:
                errors.append([{"code": "EXCEPTION", "message": str(e)}])

            if attempt < max_attempts:
                sleep_time = backoff_factor ** (attempt - 1)
                time.sleep(sleep_time)

        return None, f"Failed after {max_attempts} attempts", max_attempts

    def _execute_with_timeout(
        self, module: EDTModule, payload: Dict[str, Any], timeout_ms: int
    ) -> ModuleOutput:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(module.run, ModuleInput(data=payload))
            try:
                return future.result(timeout=timeout_ms / 1000)
            except FutureTimeoutError:
                return ModuleOutput(
                    status=ModuleStatus.FAILED,
                    data={},
                    errors=[{"code": "TIMEOUT", "message": f"Execution timeout after {timeout_ms}ms"}],
                )

    def _get_module(self, node_type: str) -> Optional[EDTModule]:
        if node_type == "ai_event_intel":
            from ai_event_intel import EventEvidenceScorer
            return EventEvidenceScorer(config_path=str(self.config_path))
        elif node_type == "signal_scorer":
            from signal_scorer import SignalScorer
            return SignalScorer(config_path=str(self.config_path))
        elif node_type == "risk_gatekeeper":
            from execution_modules import RiskGatekeeper
            return RiskGatekeeper(config_path=str(self.config_path))
        return None

    def _apply_fallback(
        self, node_type: str, fallback_config: Dict[str, Any], error: str
    ) -> Dict[str, Any]:
        if not fallback_config.get("enabled", True):
            return {"action": fallback_config.get("default_action", "BLOCK")}

        return {
            "action": fallback_config.get("default_action", "WATCH"),
            "fallback_reason": error,
            "node_type": node_type,
        }

    def run(self, input_data: ModuleInput) -> ModuleOutput:
        start_time = time.time()
        data = input_data.data

        trace_id = data.get("trace_id", f"TRC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{id(data)}")
        node_type = data.get("node_type")
        payload = data.get("payload", {})
        retry_config = data.get("retry", {})
        timeout_ms = data.get("timeout_ms", 10000)
        circuit_config = data.get("circuit_breaker", {})
        fallback_config = data.get("fallback", {"enabled": True, "default_action": "WATCH"})

        if not node_type:
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "INVALID_INPUT", "message": "node_type is required"}],
            )

        cb = self._get_circuit_breaker(node_type, circuit_config)
        if not cb.can_execute():
            fallback_data = self._apply_fallback(node_type, fallback_config, "Circuit breaker open")
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data=fallback_data,
                warnings=["CIRCUIT_OPEN: Used fallback"],
            )

        result_data, error, attempts = self._execute_with_retry(
            node_type, payload, retry_config, timeout_ms
        )

        if error:
            if "timeout" in error.lower():
                cb.record_failure()
                status = "TIMEOUT"
            else:
                cb.record_failure()
                status = "FAILED"
            fallback_data = self._apply_fallback(node_type, fallback_config, error)
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data=fallback_data,
                errors=[{"code": status, "message": error}],
                warnings=["FALLBACK_USED"],
            )

        cb.record_success()
        execution_time_ms = int((time.time() - start_time) * 1000)

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data=result_data,
        )


if __name__ == "__main__":
    import sys
    test_input = {
        "trace_id": "TEST-001",
        "node_type": "ai_event_intel",
        "payload": {"headline": "Test news", "source_url": "https://example.com"},
        "retry": {"max_attempts": 2},
        "timeout_ms": 5000,
    }
    module = OrchestratorNode()
    result = module.run(ModuleInput(data=test_input))
    print(f"Status: {result.status}")
    print(f"Data: {result.data}")
    print(f"Errors: {result.errors}")
