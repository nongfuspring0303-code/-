#!/usr/bin/env python3
"""Rollback sanitization entrypoint for EDT v2.2 rollout.

Default mode is dry-run. Apply mode creates a backup and truncates target log streams.
This script is intentionally conservative and only touches explicitly listed files.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "logs" / "rejected_events.jsonl",
    ROOT / "logs" / "quarantine_replay.jsonl",
]


def ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def backup(path: Path) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dst = path.with_suffix(path.suffix + f".{ts}.bak")
    shutil.copy2(path, dst)
    return dst


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    args = parser.parse_args()

    report = {
        "mode": args.mode,
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "targets": [],
        "warnings": [
            "DB-level sanitization is intentionally not automated here.",
            "Review backups before deleting or rotating files.",
        ],
    }

    for path in TARGETS:
        ensure_file(path)
        entry = {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "backup": None,
            "truncated": False,
        }

        if args.mode == "apply":
            entry["backup"] = str(backup(path))
            path.write_text("")
            entry["truncated"] = True
            entry["size_bytes_after"] = path.stat().st_size

        report["targets"].append(entry)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
