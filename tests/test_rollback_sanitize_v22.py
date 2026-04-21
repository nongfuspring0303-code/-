import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "rollback_sanitize_v22.py"


def _prepare_temp_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "logs").mkdir(parents=True, exist_ok=True)
    (project / "data").mkdir(parents=True, exist_ok=True)

    (project / "logs" / "rejected_events.jsonl").write_text('{"trace_id":"a"}\n', encoding="utf-8")
    (project / "logs" / "quarantine_replay.jsonl").write_text('{"trace_id":"b"}\n', encoding="utf-8")

    db = sqlite3.connect(project / "data" / "event_states.db")
    try:
        db.execute(
            """
            CREATE TABLE event_states (
                event_id TEXT PRIMARY KEY,
                internal_state TEXT NOT NULL DEFAULT 'Detected',
                lifecycle_state TEXT NOT NULL DEFAULT 'Detected',
                catalyst_state TEXT NOT NULL DEFAULT 'first_impulse',
                updated_at TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                metadata TEXT
            )
            """
        )
        db.execute(
            """
            INSERT INTO event_states(event_id, internal_state, lifecycle_state, catalyst_state, updated_at, retry_count, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt-1",
                "Detected",
                "Developing",
                "first_impulse",
                "2026-04-21T00:00:00Z",
                0,
                json.dumps(
                    {
                        "contract_version": "v2.2",
                        "legacy_contract_version": "v1.0",
                        "dual_write": True,
                        "market_data_stale": True,
                        "keep_me": "ok",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        db.commit()
    finally:
        db.close()

    return project


def test_rollback_sanitize_apply_downgrade_metadata(tmp_path: Path):
    project = _prepare_temp_project(tmp_path)

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(project),
            "--mode",
            "apply",
            "--db-action",
            "downgrade_v22_metadata",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(proc.stdout)
    assert report["mode"] == "apply"
    assert report["db_action"] == "downgrade_v22_metadata"
    assert report["db_target"]["updated_rows"] >= 1
    assert report["db_target"]["backup"]

    assert (project / "logs" / "rejected_events.jsonl").read_text(encoding="utf-8") == ""
    assert (project / "logs" / "quarantine_replay.jsonl").read_text(encoding="utf-8") == ""

    db = sqlite3.connect(project / "data" / "event_states.db")
    try:
        row = db.execute("SELECT metadata FROM event_states WHERE event_id = 'evt-1'").fetchone()
        metadata = json.loads(row[0])
    finally:
        db.close()

    assert metadata.get("compat_mode") == "legacy_v1_rollback"
    assert metadata.get("compat_contract_version") == "v1.0"
    assert "contract_version" not in metadata
    assert "dual_write" not in metadata
    assert metadata.get("keep_me") == "ok"
