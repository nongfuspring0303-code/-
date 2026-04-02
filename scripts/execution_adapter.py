#!/usr/bin/env python3
"""
Execution adapter with broker abstraction, risk gates, and state recovery.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from broker_adapter import BrokerAdapter, LiveBrokerStub, PaperBroker


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class ExecutionAdapter:
    """Execute trade orders with mode-aware broker adapter and hard risk checks."""

    def __init__(
        self,
        mode: str = "dry_run",
        audit_dir: str | None = None,
        config_path: str | None = None,
        broker: Optional[BrokerAdapter] = None,
    ):
        self.mode = mode
        self.audit_dir = Path(audit_dir) if audit_dir else Path(__file__).resolve().parent.parent / "logs"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.audit_dir / "execution_audit.jsonl"
        self.state_file = self.audit_dir / "execution_state.json"
        self.config_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml"

        self._config = self._load_config()
        self._state = self._load_state()
        self._roll_daily_state_if_needed()
        self.broker = broker if broker is not None else self._build_broker()

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _get_config(self, path: str, default: Any = None) -> Any:
        keys = path.split(".")
        value: Any = self._config
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
            if value is None:
                return default
        return value

    def _build_broker(self) -> BrokerAdapter:
        configured = str(self._get_config("modules.ExecutionAdapter.params.broker", "")).strip().lower()
        if configured == "live_stub":
            return LiveBrokerStub()
        if self.mode == "live":
            return LiveBrokerStub()
        return PaperBroker()

    def _load_state(self) -> Dict[str, Any]:
        default_state = {
            "last_reset_date": _today_utc(),
            "daily_notional": 0.0,
            "open_orders": 0,
            "processed_request_ids": [],
        }
        if not self.state_file.exists():
            return default_state
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                return default_state
            state.setdefault("last_reset_date", _today_utc())
            state.setdefault("daily_notional", 0.0)
            state.setdefault("open_orders", 0)
            state.setdefault("processed_request_ids", [])
            return state
        except Exception:
            return default_state

    def _persist_state(self) -> None:
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False)

    def _roll_daily_state_if_needed(self) -> None:
        today = _today_utc()
        if self._state.get("last_reset_date") != today:
            self._state["last_reset_date"] = today
            self._state["daily_notional"] = 0.0
            self._state["open_orders"] = 0
            self._state["processed_request_ids"] = []
            self._persist_state()

    def _is_duplicate_request(self, request_id: Optional[str]) -> bool:
        if not request_id:
            return False
        return request_id in set(self._state.get("processed_request_ids", []))

    def _mark_processed(self, request_id: Optional[str]) -> None:
        if not request_id:
            return
        ids = self._state.setdefault("processed_request_ids", [])
        if request_id not in ids:
            ids.append(request_id)
            if len(ids) > 5000:
                del ids[: len(ids) - 5000]

    def _risk_limits(self) -> Dict[str, Any]:
        return {
            "max_notional_per_order": float(
                self._get_config("modules.ExecutionAdapter.params.risk_controls.max_notional_per_order", 250000.0)
            ),
            "max_daily_notional": float(
                self._get_config("modules.ExecutionAdapter.params.risk_controls.max_daily_notional", 1000000.0)
            ),
            "max_open_orders": int(
                self._get_config("modules.ExecutionAdapter.params.risk_controls.max_open_orders", 100)
            ),
            "blocked_symbols": set(
                self._get_config("modules.ExecutionAdapter.params.risk_controls.blocked_symbols", [])
            ),
        }

    def _validate_order(self, order: Dict[str, Any]) -> Optional[str]:
        symbol = str(order.get("symbol", "")).strip().upper()
        action = str(order.get("action", "")).strip().upper()
        notional = float(order.get("notional", 0.0))

        if not symbol:
            return "missing symbol"
        if action not in ("OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT"):
            return f"unsupported action={action}"
        if notional <= 0:
            return "notional must be > 0"

        limits = self._risk_limits()
        if symbol in limits["blocked_symbols"]:
            return f"symbol {symbol} is blocked"
        if notional > limits["max_notional_per_order"]:
            return (
                f"notional {notional} exceeds max_notional_per_order "
                f"{limits['max_notional_per_order']}"
            )

        projected_daily = float(self._state.get("daily_notional", 0.0)) + notional
        if projected_daily > limits["max_daily_notional"]:
            return (
                f"projected daily notional {projected_daily} exceeds max_daily_notional "
                f"{limits['max_daily_notional']}"
            )

        if int(self._state.get("open_orders", 0)) >= limits["max_open_orders"]:
            return f"open_orders exceeds max_open_orders {limits['max_open_orders']}"
        return None

    def _write_audit(self, record: Dict[str, Any]) -> None:
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def execute(self, order: Dict[str, Any]) -> Dict[str, Any]:
        self._roll_daily_state_if_needed()

        ticket = f"EXE-{uuid.uuid4().hex[:10].upper()}"
        now = _now_iso()
        request_id = order.get("request_id")

        result: Dict[str, Any] = {
            "ticket_id": ticket,
            "mode": self.mode,
            "timestamp": now,
            "status": "accepted",
            "order": order,
        }

        if self.mode not in ("dry_run", "paper", "live"):
            result["status"] = "invalid_mode"
            result["reason"] = f"unsupported mode={self.mode}"
            self._write_audit(result)
            return result

        if self._is_duplicate_request(request_id):
            result["status"] = "duplicate_ignored"
            result["reason"] = f"request_id={request_id} already processed by execution adapter"
            self._write_audit(result)
            return result

        risk_error = self._validate_order(order)
        if risk_error:
            result["status"] = "blocked_by_risk"
            result["reason"] = risk_error
            self._write_audit(result)
            return result

        broker_result = self.broker.place_order(order)
        result["broker_result"] = broker_result

        broker_status = str(broker_result.get("status", "unknown"))
        result["status"] = broker_status
        result["broker_order_id"] = broker_result.get("broker_order_id")

        if broker_status == "accepted":
            self._state["daily_notional"] = float(self._state.get("daily_notional", 0.0)) + float(order.get("notional", 0.0))
            self._state["open_orders"] = int(self._state.get("open_orders", 0)) + 1
            self._mark_processed(request_id)
            self._persist_state()
        elif broker_status == "not_implemented":
            result["reason"] = broker_result.get("reason", "live broker adapter not implemented yet")

        self._write_audit(result)
        return result

    def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        out = self.broker.cancel_order(broker_order_id)
        if out.get("status") == "cancelled":
            self._state["open_orders"] = max(0, int(self._state.get("open_orders", 0)) - 1)
            self._persist_state()
        return out

    def get_order(self, broker_order_id: str) -> Dict[str, Any]:
        return self.broker.get_order(broker_order_id)

    def get_positions(self) -> Any:
        return self.broker.get_positions()

    def get_balance(self) -> Any:
        return self.broker.get_balance()
