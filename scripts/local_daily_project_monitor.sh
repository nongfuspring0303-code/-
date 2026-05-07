#!/usr/bin/env bash
set -euo pipefail

# EDT Local Daily Project Monitor
# Version: 1.0.1
# Security: Read-only, No mutations, No direct logic.

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOG_FILE="${PROJECT_ROOT}/logs/local_project_monitor.log"

mkdir -p "${PROJECT_ROOT}/logs"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Starting Daily Gap Scan..." >> "$LOG_FILE"

# Run the monitor - failure MUST propagate as non-zero exit
python3 "${PROJECT_ROOT}/scripts/project_gap_monitor.py" \
  --logs-dir "${PROJECT_ROOT}/logs" \
  --root "$PROJECT_ROOT" \
  >> "$LOG_FILE" 2>&1

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Scan completed successfully." >> "$LOG_FILE"
