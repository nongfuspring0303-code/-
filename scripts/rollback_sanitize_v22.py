#!/usr/bin/env python3
"""Rollback sanitization entrypoint for EDT v2.2 rollout.

Default mode is dry-run. Apply mode creates backups first.
Sanitization scope:
1) log stream truncation for quarantine/rejected streams
2) DB-level compatibility downgrade (or full purge) for event_states metadata
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METADATA_DOWNGRADE_KEYS = {
    "contract_version",
    "legacy_contract_version",
    "dual_write",
    "market_data_source",
    "market_data_present",
    "market_data_stale",
    "market_data_default_used",
    "market_data_fallback_used",
    "output_gate",
    "blockers_v2",
}


def ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def backup(path: Path) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dst = path.with_suffix(path.suffix + f".{ts}.bak")
    shutil.copy2(path, dst)
    return dst


def _ensure_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_states (
                event_id TEXT PRIMARY KEY,
                internal_state TEXT NOT NULL DEFAULT 'Detected',
                lifecycle_state TEXT NOT NULL DEFAULT 'Detected',
                catalyst_state TEXT NOT NULL DEFAULT 'first_impulse',
                updated_at TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                metadata TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _load_metadata(text: Any) -> dict[str, Any]:
    if text is None:
        return {}
    if isinstance(text, dict):
        return dict(text)
    if isinstance(text, str):
        t = text.strip()
        if not t:
            return {}
        try:
            obj = json.loads(t)
            return obj if isinstance(obj, dict) else {"_legacy_payload": obj}
        except json.JSONDecodeError:
            return {"_raw_metadata": t}
    return {"_legacy_payload": text}


def _downgrade_metadata(meta: dict[str, Any], ts: str) -> tuple[dict[str, Any], list[str]]:
    removed: list[str] = []
    out = dict(meta)
    for key in sorted(METADATA_DOWNGRADE_KEYS):
        if key in out:
            out.pop(key, None)
            removed.append(key)
    out["compat_mode"] = "legacy_v1_rollback"
    out["compat_contract_version"] = "v1.0"
    out["rollback_sanitized_at"] = ts
    return out, removed


def _sanitize_db(path: Path, mode: str, db_action: str, ts: str) -> dict[str, Any]:
    exists_before = path.exists()
    report: dict[str, Any] = {
        "path": str(path),
        "exists": exists_before,
        "db_action": db_action,
        "backup": None,
        "rows_before": 0,
        "rows_after": 0,
        "updated_rows": 0,
        "purged_rows": 0,
        "removed_keys_counter": {},
    }

    # dry-run must be read-only: never create DB as a side effect.
    if mode != "apply" and not exists_before:
        return report

    # apply mode can bootstrap an empty DB for deterministic sanitization.
    if mode == "apply":
        _ensure_db(path)
        report["exists"] = path.exists()

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM event_states").fetchone()
        report["rows_before"] = int(row["c"]) if row else 0

        if mode == "apply" and db_action != "none":
            report["backup"] = str(backup(path))

        if db_action == "none":
            pass
        elif db_action == "purge_event_states":
            if mode == "apply":
                deleted = conn.execute("DELETE FROM event_states").rowcount
                conn.commit()
                report["purged_rows"] = int(deleted or 0)
        elif db_action == "downgrade_v22_metadata":
            removed_counter: dict[str, int] = {}
            rows = conn.execute("SELECT event_id, metadata FROM event_states").fetchall()
            for row in rows:
                src_meta = _load_metadata(row["metadata"])
                dst_meta, removed = _downgrade_metadata(src_meta, ts)
                if mode == "apply":
                    conn.execute(
                        "UPDATE event_states SET metadata = ?, updated_at = ? WHERE event_id = ?",
                        (json.dumps(dst_meta, ensure_ascii=False), ts, row["event_id"]),
                    )
                if removed or src_meta != dst_meta:
                    report["updated_rows"] += 1
                for key in removed:
                    removed_counter[key] = removed_counter.get(key, 0) + 1
            if mode == "apply":
                conn.commit()
            report["removed_keys_counter"] = removed_counter
        else:
            raise ValueError(f"unsupported db_action: {db_action}")

        row = conn.execute("SELECT COUNT(*) AS c FROM event_states").fetchone()
        report["rows_after"] = int(row["c"]) if row else 0
    finally:
        conn.close()
    return report


def _build_targets(root: Path) -> tuple[list[Path], Path]:
    logs = [
        root / "logs" / "rejected_events.jsonl",
        root / "logs" / "quarantine_replay.jsonl",
    ]
    db = root / "data" / "event_states.db"
    return logs, db


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    parser.add_argument("--root", default=str(ROOT), help="Project root path")
    parser.add_argument(
        "--db-action",
        choices=["none", "downgrade_v22_metadata", "purge_event_states"],
        default="downgrade_v22_metadata",
        help="DB sanitization action for data/event_states.db",
    )
    args = parser.parse_args()
    ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    root = Path(args.root).resolve()
    log_targets, state_db = _build_targets(root)

    report = {
        "mode": args.mode,
        "db_action": args.db_action,
        "root": str(root),
        "timestamp_utc": ts,
        "targets": [],
        "db_target": {},
        "warnings": [
            "Apply mode writes backups before modifications.",
            "Use --db-action none if you only need log rollback.",
            "Use --db-action purge_event_states only for hard rollback windows.",
        ],
    }

    for path in log_targets:
        if args.mode == "apply":
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

    report["db_target"] = _sanitize_db(state_db, args.mode, args.db_action, ts)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
