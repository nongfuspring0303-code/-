#!/usr/bin/env bash
set -euo pipefail

WS_PORT="${EDT_WS_PORT:-18765}"
API_PORT="${EDT_API_PORT:-18787}"
WEB_PORT="${EDT_WEB_PORT:-18080}"

export EDT_RUNTIME_ROLE="${EDT_RUNTIME_ROLE:-dev}"
export EDT_NODE_ROLE="${EDT_NODE_ROLE:-master}"

# 使用项目级 .env 文件（已列入 .gitignore，不会提交到 Git）
uv run --env-file .env python3 scripts/run_c_module_stack.py \
  --ws-port "$WS_PORT" \
  --api-port "$API_PORT" \
  --web-port "$WEB_PORT" \
  --no-mock \
  --history-file logs/event_bus_live.jsonl
