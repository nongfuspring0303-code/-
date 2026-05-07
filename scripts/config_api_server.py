#!/usr/bin/env python3
"""
C-6 配置中心 API 服务。
提供给 canvas/config.html 的最小接口：
- GET/PUT /api/config/sector-mapping
- GET/PUT /api/config/stock-pool
- POST /api/feedback
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
import sys
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.human_feedback_center import HumanFeedbackCenter
from scripts.health_monitor import HealthMonitor
from scripts.project_trace_reader import ProjectTraceReader, build_api_envelope
from scripts.risk_gatekeeper import RiskGatekeeper, ActionType

DEFAULT_API_TOKEN = os.getenv("EDT_API_TOKEN", os.getenv("EDT_WS_TOKEN", "edt-local-dev-token"))
DEFAULT_RUNTIME_ROLE = os.getenv("EDT_RUNTIME_ROLE", "").strip().lower()


class ConfigAPIHandler(BaseHTTPRequestHandler):
    center = HumanFeedbackCenter()
    monitor = HealthMonitor()
    gatekeeper = RiskGatekeeper()
    project_reader = ProjectTraceReader()
    event_publisher = None
    auth_token = DEFAULT_API_TOKEN
    runtime_role = DEFAULT_RUNTIME_ROLE

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-EDT-Token")
        self.send_header("Access-Control-Allow-Methods", "GET,PUT,POST,PATCH,DELETE,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def _is_authorized(self) -> bool:
        if self.runtime_role == "prod" and not self.auth_token:
            return False
        if not self.auth_token:
            return True
        header_token = self.headers.get("X-EDT-Token", "").strip()
        if header_token == self.auth_token:
            return True
        auth = self.headers.get("Authorization", "").strip()
        if auth.startswith("Bearer "):
            return auth.removeprefix("Bearer ").strip() == self.auth_token
        return False

    def _require_auth(self) -> bool:
        if self._is_authorized():
            return True
        self._send_json(401, {"error": "unauthorized"})
        return False

    def do_OPTIONS(self):  # noqa: N802
        self._send_json(200, {"ok": True})

    def _project_error(
        self,
        status: int,
        message: str,
        *,
        code: str,
        trace_id: str | None = None,
        errors: list[dict] | None = None,
    ):
        payload = build_api_envelope(
            status="error",
            code=code,
            message=message,
            data=None,
            trace_id=trace_id,
            request_id=None,
            errors=errors
            or [
                {
                    "code": code,
                    "message": message,
                    "source": "config_api_server",
                    "retryable": False,
                    "severity": "error",
                }
            ],
            retryable=False,
        )
        self._send_json(status, payload)

    def _project_limit_from_query(self, query: dict[str, list[str]]) -> int:
        raw_limit = query.get("limit", ["20"])[0]
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return 20
        if limit < 1:
            return 1
        if limit > 100:
            return 100
        return limit

    def _send_project_payload(self, payload: dict, *, default_status: int = 200):
        http_status = int(payload.get("http_status") or default_status)
        if payload.get("status") == "error" and payload.get("http_status") is None:
            http_status = 500
        self._send_json(
            http_status,
            build_api_envelope(
                status=payload.get("status", "error"),
                code=payload.get("code", "OK"),
                message=payload.get("message", "Project trace request failed."),
                data=payload.get("data"),
                trace_id=payload.get("trace_id"),
                errors=payload.get("errors", []),
                retryable=False,
            ),
        )

    def _handle_project_get(self) -> bool:
        reader = self.project_reader
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/api/project/traces/latest":
                self._send_project_payload(reader.latest_traces(limit=self._project_limit_from_query(query)))
                return True
            if path.startswith("/api/project/trace/"):
                trace_id = unquote(path.rsplit("/", 1)[-1]).strip()
                self._send_project_payload(reader.trace_detail(trace_id))
                return True
            if path == "/api/project/scorecards/latest":
                self._send_project_payload(reader.latest_scorecard())
                return True
            if path == "/api/project/gap-report":
                self._send_project_payload(reader.gap_report())
                return True
            if path == "/api/project/system-health":
                self._send_project_payload(reader.system_health())
                return True
        except Exception as exc:  # noqa: BLE001
            self.log_error("project endpoint failed: %s", str(exc))
            self._project_error(
                500,
                "Project endpoint failed to load safely.",
                code="INTERNAL_ERROR",
                errors=[
                    {
                        "code": "INTERNAL_ERROR",
                        "message": "Project endpoint failed to load safely.",
                        "source": "config_api_server",
                        "retryable": False,
                        "severity": "error",
                    }
                ],
            )
            return True
        if path.startswith("/api/project/"):
            self._project_error(404, "Project endpoint not found.", code="NOT_FOUND")
            return True
        return False

    def do_GET(self):  # noqa: N802
        if not self._require_auth():
            return
        if self._handle_project_get():
            return
        if self.path == "/api/config/sector-mapping":
            self._send_json(200, self.center.get_sector_mapping())
            return
        if self.path == "/api/config/stock-pool":
            self._send_json(200, self.center.get_stock_pool())
            return
        if self.path.startswith("/api/feedback/export/"):
            target = self.path.rsplit("/", 1)[-1]
            self._send_json(200, self.center.export_feedback_package(target))
            return
        if self.path == "/api/monitor/status":
            self._send_json(200, self.monitor.status())
            return
        if self.path == "/api/trade/pending":
            self._send_json(200, {"items": self.gatekeeper.get_pending_confirmations()})
            return
        self._send_json(404, {"error": "not found"})

    def _handle_project_method_not_allowed(self) -> bool:
        if self.path.startswith("/api/project/"):
            self._project_error(
                405,
                "Project endpoints are read-only.",
                code="METHOD_NOT_ALLOWED",
            )
            return True
        return False

    def do_PUT(self):  # noqa: N802
        if not self._require_auth():
            return
        if self._handle_project_method_not_allowed():
            return
        payload = self._read_json()
        if self.path == "/api/config/sector-mapping":
            self.center.update_sector_mapping(payload)
            self._send_json(200, {"status": "ok"})
            return
        if self.path == "/api/config/stock-pool":
            self.center.update_stock_pool(payload)
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if not self._require_auth():
            return
        if self._handle_project_method_not_allowed():
            return
        if self.path == "/api/monitor/report":
            payload = self._read_json()
            required = ["module", "signal_type", "severity", "message", "trace_id"]
            missing = [k for k in required if k not in payload or payload.get(k) in ("", None)]
            if missing:
                self._send_json(400, {"error": "missing fields", "fields": missing})
                return
            resp = self.monitor.report(**payload)
            self._send_json(200, resp)
            return

        if self.path == "/api/trade/execute":
            payload = self._read_json()
            if not payload.get("opportunity"):
                self._send_json(400, {"error": "missing opportunity"})
                return
            opportunity = payload["opportunity"]
            check = self.gatekeeper.check_opportunity(opportunity)

            if check.action == ActionType.BLOCK:
                self._send_json(403, {
                    "status": "blocked",
                    "action": check.action.value,
                    "reason": check.reason,
                    "risk_flags": [{"type": f.type, "level": f.level, "description": f.description} for f in check.risk_flags],
                })
                return

            if check.action == ActionType.PENDING_CONFIRM:
                self._send_json(202, {
                    "status": "pending_confirm",
                    "action": check.action.value,
                    "confirm_id": check.confirm_id,
                    "reason": check.reason,
                })
                return

            self._publish_event("execution_request", {
                "symbol": opportunity.get("symbol"),
                "trace_id": payload.get("trace_id"),
                "source": "C-module",
                "opportunity": opportunity,
            }, trace_id=payload.get("trace_id"))
            self._send_json(200, {
                "status": "executed",
                "action": check.action.value,
                "reason": check.reason,
            })
            return

        if self.path == "/api/trade/confirm":
            payload = self._read_json()
            confirm_id = payload.get("confirm_id")
            approved = bool(payload.get("approved", False))
            if not confirm_id:
                self._send_json(400, {"error": "missing confirm_id"})
                return

            ok = self.gatekeeper.confirm_action(confirm_id, approved=approved)
            if not ok:
                self._send_json(404, {"status": "not_found_or_timeout"})
                return

            info = self.gatekeeper.get_confirmation(confirm_id)
            self._publish_event("execution_confirm", {
                "confirm_id": confirm_id,
                "approved": approved,
                "symbol": info.get("symbol") if info else None,
            })
            self._send_json(200, {"status": "confirmed", "confirm_id": confirm_id, "approved": approved})
            return

        if self.path in {"/api/ingest/sector-update", "/api/ingest/opportunity-update", "/api/ingest/event-update"}:
            payload = self._read_json()
            kind = self.path.split("/")[-1]
            event_type = kind.replace("-", "_")
            missing = [k for k in ["trace_id", "schema_version"] if not payload.get(k)]
            if missing:
                self._send_json(400, {"error": "missing fields", "fields": missing})
                return
            ok = self._publish_event(event_type, payload, trace_id=payload.get("trace_id"))
            if not ok:
                self._send_json(500, {"status": "publish_failed", "event_type": event_type})
                return
            self._send_json(200, {"status": "accepted", "event_type": event_type})
            return

        if self.path != "/api/feedback":
            self._send_json(404, {"error": "not found"})
            return
        payload = self._read_json()
        required = [
            "trace_id",
            "source_module",
            "target_module",
            "feedback_type",
            "original_value",
            "corrected_value",
            "reason",
        ]
        missing = [k for k in required if k not in payload or payload.get(k) in ("", None)]
        if missing:
            self._send_json(400, {"error": "missing fields", "fields": missing})
            return
        resp = self.center.submit_feedback(**payload)
        self._send_json(200, resp)

    def do_PATCH(self):  # noqa: N802
        if not self._require_auth():
            return
        if self._handle_project_method_not_allowed():
            return
        self._send_json(404, {"error": "not found"})

    def do_DELETE(self):  # noqa: N802
        if not self._require_auth():
            return
        if self._handle_project_method_not_allowed():
            return
        self._send_json(404, {"error": "not found"})

    def _publish_event(self, event_type: str, payload: dict, trace_id: Optional[str] = None):
        if not self.event_publisher:
            return False
        try:
            self.event_publisher(event_type=event_type, payload=payload, trace_id=trace_id)
            return True
        except Exception as e:
            self.log_error("publish event failed: %s", str(e))
            return False


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def create_server(host: str = "127.0.0.1", port: int = 18787, event_publisher=None) -> HTTPServer:
    if event_publisher is not None:
        ConfigAPIHandler.event_publisher = staticmethod(event_publisher)
    ConfigAPIHandler.auth_token = DEFAULT_API_TOKEN
    if DEFAULT_RUNTIME_ROLE:
        ConfigAPIHandler.runtime_role = DEFAULT_RUNTIME_ROLE
    return ThreadingHTTPServer((host, port), ConfigAPIHandler)


def run(host: str = "127.0.0.1", port: int = 18787):
    server = create_server(host, port)
    print(f"Config API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
