#!/usr/bin/env bash
set -euo pipefail

WS_PORT="${EDT_WS_PORT:-18765}"
API_PORT="${EDT_API_PORT:-18787}"
WEB_PORT="${EDT_WEB_PORT:-18080}"

python3 scripts/run_c_module_stack.py   --ws-port "$WS_PORT"   --api-port "$API_PORT"   --web-port "$WEB_PORT"
