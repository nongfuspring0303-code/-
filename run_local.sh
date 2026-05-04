#!/usr/bin/env bash
set -euo pipefail

# 清理旧进程
kill $(lsof -ti :18765 -P 2>/dev/null) 2>/dev/null || true
sleep 1

WS_PORT="${EDT_WS_PORT:-18765}"
API_PORT="${EDT_API_PORT:-18787}"
WEB_PORT="${EDT_WEB_PORT:-18080}"

export EDT_RUNTIME_ROLE="${EDT_RUNTIME_ROLE:-dev}"
export EDT_NODE_ROLE="${EDT_NODE_ROLE:-master}"

uv run --with pyyaml --with requests --with websockets --with pandas --with yfinance --with jsonschema python3 scripts/run_c_module_stack.py   --ws-port "$WS_PORT"   --api-port "$API_PORT"   --web-port "$WEB_PORT"   --no-mock   --history-file logs/event_bus_live.jsonl
