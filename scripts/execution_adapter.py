#!/usr/bin/env python3
"""
Execution adapter for production-grade workflow.
Default mode is dry-run; can be extended to real broker API.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class ExecutionAdapter:
    """Execute trade orders with a pluggable mode."""

    def __init__(self, mode: str = "dry_run", audit_dir: str | None = None):
        self.mode = mode
        self.audit_dir = Path(audit_dir) if audit_dir else Path(__file__).resolve().parent.parent / "logs"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.audit_dir / "execution_audit.jsonl"
        self._audit_lock = threading.Lock()

    def execute(self, order: Dict[str, Any]) -> Dict[str, Any]:
        ticket = f"EXE-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        result = {
            "ticket_id": ticket,
            "mode": self.mode,
            "timestamp": now,
            "status": "accepted",
            "order": order,
        }

        if self.mode == "live":
            # Production extension point: place order to broker API.
            result["status"] = "not_implemented"
            result["reason"] = "live broker adapter not implemented yet"
        elif self.mode in ("dry_run", "paper"):
            result["status"] = "accepted"
        else:
            result["status"] = "invalid_mode"
            result["reason"] = f"unsupported mode={self.mode}"

        with self._audit_lock:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result
