#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

echo "[1/4] pytest"
python3 -m pytest -q

echo "[2/4] system healthcheck (prod mode)"
python3 scripts/system_healthcheck.py --mode prod

echo "[3/4] mapping/coverage checks"
python3 scripts/verify_mapping_quality.py
python3 scripts/verify_sector_coverage.py


echo "[4/4] dedupe check"
python3 scripts/verify_dedupe_accuracy.py

echo "✅ verify_phase3_fullcheck.sh completed"
