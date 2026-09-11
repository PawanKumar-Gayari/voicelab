"""PostgreSQL event/snapshot store for VoiceLab.

The store mirrors the SQLite contract: one durable snapshot per session, a
monotonic per-session version, and an immutable append-only event stream.
Writes lock the session row in a transaction, merge append-only fields, bump
version, update the snapshot, and append the event before commit.
"""
from __future__ import annotations

import copy
import json
import os
import time
from typing import Any

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised only when PostgreSQL backend is selected
    psycopg = None


def database_url() -> str:
    return os.getenv("VOICELAB_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()


def _require_driver():
    if psycopg is None:
        raise RuntimeError("PostgreSQL backend requires psycopg[binary].")
    url = database_url()
    if not url:
        raise RuntimeError("VOICELAB_DATABASE_URL is required for the PostgreSQL backend.")
    return url


def connect():
    url = _require_driver()
    return psycopg.connect(url, connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")))


def ensure_schema() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS research_sessions (
                    session_id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    state_json JSONB NOT NULL,
                    version BIGINT NOT NULL DEFAULT 1,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS research_events (
                    event_id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
                    version BIGINT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json JSONB NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    UNIQUE(session_id, version)
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_research_events_session ON research_events(session_id, event_id)")
        conn.commit()


def load_session_row(session_id: str):
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT session_id, owner_id, state_json, version FROM research_sessions WHERE session_id=%s", (session_id,))
            return cur.fetchone()


def persist(
    session: Any,
    desired: dict[str, Any],
    baseline: dict[str, Any],
    event_type: str,
    merge_changes,
    json_default,
) -> tuple[dict[str, Any], int]:
    """Serialize a session mutation under a PostgreSQL row lock."""
    ensure_schema()
    for attempt in range(4):
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT session_id, owner_id, state_json, version FROM research_sessions WHERE session_id=%s FOR UPDATE", (session.session_id,))
                    row = cur.fetchone()
                    now = time.time()
                    if row is None:
                        new_version = 1
                        merged = copy.deepcopy(desired)
                        cur.execute(
                            "INSERT INTO research_sessions(session_id, owner_id, state_json, version, created_at, updated_at) VALUES(%s,%s,%s::jsonb,%s,%s,%s)",
                            (session.session_id, merged.get("owner_id"), json.dumps(merged, default=json_default), new_version, now, now),
                        )
                        changed = list(desired.keys())
                    else:
                        latest = row[2] if isinstance(row[2], dict) else json.loads(row[2])
                        merged, changed = merge_changes(latest, baseline, desired)
                        if not changed:
                            conn.commit()
                            return latest, int(row[3])
                        new_version = int(row[3]) + 1
                        cur.execute(
                            "UPDATE research_sessions SET owner_id=%s, state_json=%s::jsonb, version=%s, updated_at=%s WHERE session_id=%s",
                            (merged.get("owner_id"), json.dumps(merged, default=json_default), new_version, now, session.session_id),
                        )
                    payload = {"changed": changed, "state": merged}
                    cur.execute(
                        "INSERT INTO research_events(session_id, version, event_type, payload_json, created_at) VALUES(%s,%s,%s,%s::jsonb,%s)",
                        (session.session_id, new_version, event_type, json.dumps(payload, default=json_default), now),
                    )
                conn.commit()
                return merged, new_version
        except Exception as exc:
            if psycopg is not None and isinstance(exc, psycopg.errors.SerializationFailure) and attempt < 3:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
    raise RuntimeError("PostgreSQL persistence failed after retries")


def events(session_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT event_id, version, event_type, payload_json, created_at FROM research_events WHERE session_id=%s ORDER BY event_id ASC LIMIT %s", (session_id, max(1, min(int(limit), 10000))))
            rows = cur.fetchall()
    return [
        {"event_id": r[0], "version": r[1], "event_type": r[2], "payload": r[3] if isinstance(r[3], dict) else json.loads(r[3]), "created_at": r[4]}
        for r in rows
    ]


def delete(session_id: str) -> bool:
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM research_sessions WHERE session_id=%s", (session_id,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def clear() -> None:
    ensure_schema()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM research_sessions")
        conn.commit()
