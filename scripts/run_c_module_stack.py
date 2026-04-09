#!/usr/bin/env python3
"""
C 模块一键联调启动脚本。

启动内容：
1) WebSocket 事件总线 (8765)
2) 配置中心/反馈/监控 API (8787)
3) 静态页面服务 (8080)
4) Mock 事件流生产器（持续推送 event/sector/opportunity）
"""

from __future__ import annotations

import argparse
import asyncio
import random
import os
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import sys
import yaml

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_api_server import create_server
from scripts.event_bus import EventBus
from scripts.health_monitor import HealthMonitor


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "edt-modules-config.yaml"


def load_runtime_config(config_path: Path) -> dict:
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValueError(f"Invalid runtime config: {config_path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid runtime config root type: expected mapping, got {type(payload).__name__}")
    return payload.get("runtime", {}) or {}


def resolve_mock_producer_enabled(
    role: str,
    mode: str,
    allow_non_dev_mock: bool,
    disable_mock: bool,
) -> bool:
    if disable_mock or mode == "off":
        return False
    if mode == "on":
        if role != "dev" and not allow_non_dev_mock:
            raise ValueError("Mock producer is dev-only by default. Use --allow-non-dev-mock for non-dev role.")
        return True
    return role == "dev"


def validate_mock_mode(mode: str) -> str:
    normalized = str(mode or "auto").strip().lower()
    if normalized not in {"auto", "on", "off"}:
        raise ValueError(f"Invalid mock_mode '{mode}'. Allowed: auto|on|off")
    return normalized


def resolve_history_file(runtime_cfg: dict, history_file: str | None = None) -> str | None:
    if not history_file:
        stack_cfg = runtime_cfg.get("c_module_stack", {}) if isinstance(runtime_cfg, dict) else {}
        history_file = stack_cfg.get("history_file")
    if not history_file:
        return None
    path = Path(history_file)
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


def resolve_history_file_path(history_file: str | None) -> str | None:
    """Backward-compatible wrapper for tests/imports."""
    return resolve_history_file({}, history_file)



def start_static_server(host: str, port: int, directory: Path) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer((host, port), handler)
    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def start_api_server(host: str, port: int, publisher=None):
    server = create_server(host, port, event_publisher=publisher)
    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def build_mock_event(trace_id: str):
    headlines = [
        "美联储暗示降息节奏放缓",
        "AI 算力资本开支继续上修",
        "原油价格单日上涨 3%",
        "美国非农就业数据超预期",
    ]
    sectors = [
        {"name": "科技", "direction": "LONG", "impact_score": 0.86, "confidence": 0.9},
        {"name": "半导体", "direction": "LONG", "impact_score": 0.91, "confidence": 0.93},
        {"name": "航空", "direction": "SHORT", "impact_score": 0.62, "confidence": 0.81},
    ]
    opportunities = [
        {
            "symbol": "NVDA",
            "name": "英伟达",
            "sector": "科技",
            "signal": "LONG",
            "entry_zone": {"support": 1120, "resistance": 1180},
            "risk_flags": [{"type": "volatility", "level": "medium", "description": "波动较大"}],
            "final_action": "PENDING_CONFIRM",
            "reasoning": "AI 资本开支持续上修，景气度延续",
            "confidence": 0.87,
        },
        {
            "symbol": "AAPL",
            "name": "苹果",
            "sector": "科技",
            "signal": "LONG",
            "entry_zone": {"support": 208, "resistance": 219},
            "risk_flags": [{"type": "liquidity", "level": "low", "description": "流动性充足"}],
            "final_action": "EXECUTE",
            "reasoning": "板块共振，风险可控",
            "confidence": 0.82,
        },
    ]

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    request_id = f"REQ-{trace_id}"
    batch_id = f"BATCH-{trace_id}"
    return {
        "event_update": {
            "type": "event_update",
            "trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "schema_version": "v1.0",
            "headline": random.choice(headlines),
            "source": "MockFeed",
            "severity": random.choice(["E1", "E2", "E3"]),
            "timestamp": now,
        },
        "sector_update": {
            "type": "sector_update",
            "trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "schema_version": "v1.0",
            "sectors": sectors,
            "conduction_chain": [
                {"level": "macro", "name": "流动性", "relation": "affects_above"},
                {"level": "sector", "name": "科技", "relation": "same"},
                {"level": "theme", "name": "AI基础设施", "relation": "affects_below"},
            ],
            "timestamp": now,
        },
        "opportunity_update": {
            "type": "opportunity_update",
            "trace_id": trace_id,
            "request_id": request_id,
            "batch_id": batch_id,
            "schema_version": "v1.0",
            "opportunities": opportunities,
            "timestamp": now,
        },
    }


async def mock_producer(bus: EventBus, monitor: HealthMonitor, interval_sec: float):
    idx = 1
    while True:
        trace_id = f"evt_mock_{idx:06d}"
        payloads = build_mock_event(trace_id)

        await bus.publish("event_update", payloads["event_update"], trace_id=trace_id)
        await asyncio.sleep(0.15)
        await bus.publish("sector_update", payloads["sector_update"], trace_id=trace_id)
        await asyncio.sleep(0.15)
        await bus.publish("opportunity_update", payloads["opportunity_update"], trace_id=trace_id)

        if random.random() < 0.3:
            monitor.report(
                module=random.choice(["A", "B"]),
                signal_type=random.choice(["timeout", "degrade"]),
                severity=random.choice(["low", "medium", "high"]),
                message="mock health signal",
                trace_id=trace_id,
            )

        idx += 1
        await asyncio.sleep(interval_sec)


async def main():
    parser = argparse.ArgumentParser(description="Run C module local integration stack")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--ws-host", default="127.0.0.1")
    parser.add_argument("--ws-port", type=int, default=int(os.getenv("EDT_WS_PORT", "18765")))
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=int(os.getenv("EDT_API_PORT", "18787")))
    parser.add_argument("--web-host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=int(os.getenv("EDT_WEB_PORT", "18080")))
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--role", choices=["dev", "staging", "prod"], default=None)
    parser.add_argument("--mock-mode", choices=["auto", "on", "off"], default=None)
    parser.add_argument("--allow-non-dev-mock", action="store_true")
    parser.add_argument("--history-file", default=None, help="jsonl history file path for EventBus")
    parser.add_argument("--no-mock", action="store_true", help="disable mock producer, wait for A/B ingest")
    args = parser.parse_args()

    runtime_cfg = load_runtime_config(Path(args.config))
    stack_cfg = runtime_cfg.get("c_module_stack", {}) or {}
    mock_cfg = stack_cfg.get("mock_producer", {}) or {}

    role = args.role or runtime_cfg.get("role") or "dev"
    node_role = str(os.getenv("EDT_NODE_ROLE", runtime_cfg.get("node_role", "master"))).strip().lower() or "master"
    mock_mode = validate_mock_mode(args.mock_mode or mock_cfg.get("default_mode") or "auto")
    allow_non_dev_mock = args.allow_non_dev_mock or bool(mock_cfg.get("allow_non_dev", False))
    history_file = resolve_history_file(runtime_cfg, args.history_file or stack_cfg.get("history_file"))

    try:
        enable_mock = resolve_mock_producer_enabled(role, mock_mode, allow_non_dev_mock, args.no_mock)
    except ValueError as exc:
        parser.error(str(exc))

    bus = EventBus(host=args.ws_host, port=args.ws_port, history_file=history_file)
    monitor = HealthMonitor(base_dir=str(PROJECT_ROOT))

    loop = asyncio.get_running_loop()

    def publish_from_api(event_type: str, payload: dict, trace_id: str | None = None):
        fut = asyncio.run_coroutine_threadsafe(
            bus.publish(event_type, payload, trace_id=trace_id),
            loop,
        )
        fut.result(timeout=5)

    api_server = start_api_server(args.api_host, args.api_port, publisher=publish_from_api)
    static_server = start_static_server(args.web_host, args.web_port, PROJECT_ROOT)

    print("[C-Module Stack] started")
    print(f"- WebSocket: ws://{args.ws_host}:{args.ws_port}")
    print(f"- API:       http://{args.api_host}:{args.api_port}")
    print(f"- Web:       http://{args.web_host}:{args.web_port}/canvas/index.html")
    print(f"- Config:    http://{args.web_host}:{args.web_port}/canvas/config.html")
    print(f"- Monitor:   http://{args.web_host}:{args.web_port}/canvas/monitor.html")
    print("- Ingest:    POST /api/ingest/{event-update|sector-update|opportunity-update}")
    print(f"- Role:      {role}")
    print(f"- NodeRole:  {node_role}")
    print(f"- Mock:      {'enabled' if enable_mock else 'disabled'} ({mock_mode})")
    print("Press Ctrl+C to stop.")

    bus_task = asyncio.create_task(bus.start())
    producer_task = None
    if enable_mock and node_role != "worker":
        producer_task = asyncio.create_task(mock_producer(bus, monitor, args.interval))

    try:
        if producer_task:
            await asyncio.gather(bus_task, producer_task)
        else:
            await bus_task
    except asyncio.CancelledError:
        pass
    finally:
        if producer_task:
            producer_task.cancel()
        await bus.stop()
        api_server.shutdown()
        static_server.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[C-Module Stack] stopped")
