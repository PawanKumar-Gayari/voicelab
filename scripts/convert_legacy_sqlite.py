#!/usr/bin/env python3
"""Windows-safe legacy VoiceLab SQLite -> current SQLite converter."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

CURRENT_SCHEMA = """
CREATE TABLE research_sessions (
    session_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE research_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    UNIQUE(session_id, version)
);
CREATE INDEX idx_research_events_session_event
ON research_events(session_id, event_id);
"""

def args():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--owner-id", default="admin")
    p.add_argument("--expected-sessions", type=int, default=48)
    p.add_argument("--force", action="store_true")
    p.add_argument("--stale-temp-glob", default=None)
    return p.parse_args()

def open_source_readonly(path: Path):
    if not path.is_file():
        raise RuntimeError(f"Source SQLite database does not exist: {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn

def read_legacy(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "research_sessions" not in tables:
        raise RuntimeError("Legacy database has no research_sessions table.")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(research_sessions)")}
    missing = {"session_id", "state_json"} - cols
    if missing:
        raise RuntimeError(f"Legacy schema missing columns: {sorted(missing)}")

    rows = conn.execute(
        "SELECT session_id, state_json FROM research_sessions ORDER BY session_id"
    ).fetchall()

    for sid, raw in rows:
        if not sid:
            raise RuntimeError("Legacy database contains an empty session_id.")
        try:
            state = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid state_json for session {sid}: {exc}") from exc
        if not isinstance(state, dict):
            raise RuntimeError(f"state_json for session {sid} is not an object.")
    return rows

def write_output(path, rows, owner_id):
    if path.exists():
        raise FileExistsError(f"Output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(CURRENT_SCHEMA)
        now = time.time()

        for sid, state_json in rows:
            conn.execute(
                """INSERT INTO research_sessions
                (session_id, owner_id, state_json, version, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)""",
                (sid, owner_id, state_json, now, now),
            )
            payload = json.dumps({
                "source": "legacy_sqlite",
                "imported": True,
                "legacy_session_id": sid,
            }, separators=(",", ":"), sort_keys=True)
            conn.execute(
                """INSERT INTO research_events
                (session_id, version, event_type, payload_json, created_at)
                VALUES (?, 1, 'legacy_import', ?, ?)""",
                (sid, payload, now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    else:
        # Explicitly close BEFORE any validation or filesystem operation.
        conn.close()

def validate_output(path, expected):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        sessions = conn.execute(
            "SELECT COUNT(*) FROM research_sessions").fetchone()[0]
        events = conn.execute(
            "SELECT COUNT(*) FROM research_events").fetchone()[0]
        invalid_json = conn.execute(
            "SELECT COUNT(*) FROM research_sessions WHERE json_valid(state_json)=0"
        ).fetchone()[0]
        missing_events = conn.execute(
            """SELECT COUNT(*) FROM research_sessions s
               LEFT JOIN research_events e
                 ON e.session_id=s.session_id AND e.version=s.version
               WHERE e.event_id IS NULL"""
        ).fetchone()[0]

        if sessions != expected:
            raise RuntimeError(
                f"Validation failed: expected {expected} sessions, got {sessions}")
        if events != sessions:
            raise RuntimeError(
                f"Validation failed: expected {sessions} events, got {events}")
        if invalid_json:
            raise RuntimeError(f"Validation failed: {invalid_json} invalid JSON rows")
        if missing_events:
            raise RuntimeError(
                f"Validation failed: {missing_events} sessions missing import events")
        return sessions, events
    finally:
        # Validation connection is also closed before cleanup.
        conn.close()

def cleanup_stale(output, pattern):
    if not pattern:
        return 0
    removed = 0
    for p in output.parent.glob(pattern):
        if p.resolve() == output.resolve():
            continue
        if p.is_file():
            p.unlink()
            removed += 1
    return removed

def main():
    a = args()
    source = Path(a.source).resolve()
    output = Path(a.output).resolve()

    if source == output:
        raise RuntimeError("Source and output must be different.")
    if output.exists():
        if not a.force:
            raise RuntimeError(
                f"Output already exists: {output}; refusing to overwrite without --force")
        output.unlink()

    source_stat = source.stat()

    source_conn = None
    try:
        source_conn = open_source_readonly(source)
        rows = read_legacy(source_conn)
    finally:
        if source_conn is not None:
            source_conn.close()

    if len(rows) != a.expected_sessions:
        raise RuntimeError(
            f"Legacy database contains {len(rows)} sessions; expected {a.expected_sessions}")

    # No source connection remains open here.
    write_output(output, rows, a.owner_id)

    # All writer connections are closed before validation.
    sessions, events = validate_output(output, a.expected_sessions)

    # Source must still be unchanged.
    after = source.stat()
    if (source_stat.st_size, source_stat.st_mtime_ns) != (
        after.st_size, after.st_mtime_ns
    ):
        raise RuntimeError("SAFETY FAILURE: original source database changed.")

    # Cleanup is intentionally last: only after successful validation.
    removed = cleanup_stale(output, a.stale_temp_glob)

    print("CONVERSION PASS")
    print(f"Source: {source}")
    print(f"Output: {output}")
    print(f"Sessions verified: {sessions}")
    print(f"Events verified: {events}")
    print("Original database: preserved")
    print("Backup database: not touched")
    print("All SQLite connections: closed before validation/cleanup")
    print(f"Stale temp files removed: {removed}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CONVERSION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
