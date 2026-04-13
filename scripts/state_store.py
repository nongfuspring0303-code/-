#!/usr/bin/env python3
"""
SQLite-based event state store for lifecycle tracking.

Stores and retrieves event lifecycle states between runs,
enabling stateful progression of the same event over time.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


_SCHEMA = """
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


class EventStateStore:
    """Persistent event state store backed by SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = str(Path(__file__).resolve().parent.parent / "data" / "event_states.db")
        self._db_path = db_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def get_state(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored state for an event. Returns None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM event_states WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result.get("metadata"):
            import json
            result["metadata"] = json.loads(result["metadata"])
        return result

    def upsert_state(self, event_id: str, state: Dict[str, Any]) -> None:
        """Insert or update event state."""
        import json
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        metadata = state.get("metadata")
        if metadata is not None and not isinstance(metadata, str):
            metadata = json.dumps(metadata)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO event_states (
                    event_id, internal_state, lifecycle_state,
                    catalyst_state, updated_at, retry_count, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    internal_state = excluded.internal_state,
                    lifecycle_state = excluded.lifecycle_state,
                    catalyst_state = excluded.catalyst_state,
                    updated_at = excluded.updated_at,
                    retry_count = excluded.retry_count,
                    metadata = excluded.metadata
                """,
                (
                    event_id,
                    state.get("internal_state", "Detected"),
                    state.get("lifecycle_state", "Detected"),
                    state.get("catalyst_state", "first_impulse"),
                    state.get("updated_at", now),
                    state.get("retry_count", 0),
                    metadata,
                ),
            )
            conn.commit()

    def increment_retry(self, event_id: str) -> int:
        """Increment retry count for an event. Returns new count."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE event_states SET retry_count = retry_count + 1 WHERE event_id = ?",
                (event_id,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT retry_count FROM event_states WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return row["retry_count"] if row else 0

    def delete_state(self, event_id: str) -> bool:
        """Delete event state. Returns True if deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM event_states WHERE event_id = ?", (event_id,)
            )
            conn.commit()
        return cursor.rowcount > 0
