#!/usr/bin/env python3
"""
Broker abstraction layer for execution adapter.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_order(self, broker_order_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_balance(self) -> Dict[str, Any]:
        pass


class PaperBroker(BrokerAdapter):
    def __init__(self):
        self.orders: Dict[str, Dict[str, Any]] = {}

    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        broker_order_id = f"PAPER-{uuid.uuid4().hex[:12].upper()}"
        record = {
            "broker_order_id": broker_order_id,
            "status": "accepted",
            "timestamp": _now_iso(),
            "order": order,
            "filled_qty": 0.0,
            "avg_fill_price": None,
            "source": "paper",
        }
        self.orders[broker_order_id] = record
        return record

    def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        record = self.orders.get(broker_order_id)
        if not record:
            return {
                "broker_order_id": broker_order_id,
                "status": "not_found",
                "source": "paper",
            }
        record["status"] = "cancelled"
        record["cancelled_at"] = _now_iso()
        return record

    def get_order(self, broker_order_id: str) -> Dict[str, Any]:
        record = self.orders.get(broker_order_id)
        if not record:
            return {
                "broker_order_id": broker_order_id,
                "status": "not_found",
                "source": "paper",
            }
        return record

    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def get_balance(self) -> Dict[str, Any]:
        return {
            "currency": "USD",
            "equity": 1000000.0,
            "available": 1000000.0,
            "source": "paper",
        }


class LiveBrokerStub(BrokerAdapter):
    def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "not_implemented",
            "reason": "live broker adapter not configured yet",
            "source": "live_stub",
            "order": order,
            "timestamp": _now_iso(),
        }

    def cancel_order(self, broker_order_id: str) -> Dict[str, Any]:
        return {
            "broker_order_id": broker_order_id,
            "status": "not_implemented",
            "reason": "live broker adapter not configured yet",
            "source": "live_stub",
        }

    def get_order(self, broker_order_id: str) -> Dict[str, Any]:
        return {
            "broker_order_id": broker_order_id,
            "status": "not_implemented",
            "reason": "live broker adapter not configured yet",
            "source": "live_stub",
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def get_balance(self) -> Dict[str, Any]:
        return {
            "status": "not_implemented",
            "reason": "live broker adapter not configured yet",
            "source": "live_stub",
        }
