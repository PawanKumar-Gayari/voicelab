#!/usr/bin/env python3
"""Resumable, checksum-verified SQLite -> PostgreSQL migration for VoiceLab.

Safety model:
- PostgreSQL target must be empty for a new migration job.
- A migration job records the source fingerprint and progress in PostgreSQL.
- Each batch is committed independently, so an interrupted run can resume.
- Existing target rows are never overwritten silently: identical rows are skipped;
  conflicting rows abort the migration.
- Final row counts and SHA-256 checksums must match before a job is marked complete.
- Rollback is deliberately conservative: it is allowed only when the completed
  target still exactly matches the source fingerprint. Stop application writers first.

Usage examples:
  python scripts/migrate_sqlite_to_postgres.py --sqlite ./voicelab_state.db --dry-run
  python scripts/migrate_sqlite_to_postgres.py --sqlite ./voicelab_state.db --job-id <id>
  python scripts/migrate_sqlite_to_postgres.py --sqlite ./voicelab_state.db --job-id <id> --rollback

Set VOICELAB_DATABASE_URL (or DATABASE_URL) for PostgreSQL connectivity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PostgreSQL migration requires psycopg[binary].") from exc

from app.agent import postgres_store

SCHEMA_VERSION = 1
DEFAULT_BATCH_SIZE = 250
TABLES = ("research_sessions", "research_events")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def row_bytes(table: str, row: tuple[Any, ...]) -> bytes:
    if table == "research_sessions":
        session_id, owner_id, state_json, version, created_at, updated_at = row
        state = state_json if isinstance(state_json, dict) else json.loads(state_json)
        payload = {
            "session_id": session_id,
            "owner_id": owner_id,
            "state_json": state,
            "version": int(version),
            "created_at": created_at,
            "updated_at": updated_at,
        }
    else:
        event_id, session_id, version, event_type, payload_json, created_at = row
        payload = payload_json if isinstance(payload_json, dict) else json.loads(payload_json)
        payload = {
            "event_id": int(event_id),
            "session_id": session_id,
            "version": int(version),
            "event_type": event_type,
            "payload_json": payload,
            "created_at": created_at,
        }
    return (canonical_json(payload) + "\n").encode("utf-8")


def sqlite_connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise RuntimeError(f"SQLite database does not exist: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def source_rows(conn: sqlite3.Connection, table: str) -> Iterable[tuple[Any, ...]]:
    if table == "research_sessions":
        query = "SELECT session_id, owner_id, state_json, version, created_at, updated_at FROM research_sessions ORDER BY session_id"
    else:
        query = "SELECT event_id, session_id, version, event_type, payload_json, created_at FROM research_events ORDER BY event_id"
    for row in conn.execute(query):
        yield tuple(row)


def source_stats(conn: sqlite3.Connection, table: str) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    for row in source_rows(conn, table):
        digest.update(row_bytes(table, row))
        count += 1
    return count, digest.hexdigest()


def source_fingerprint(conn: sqlite3.Connection) -> dict[str, Any]:
    stats = {}
    for table in TABLES:
        try:
            count, checksum = source_stats(conn, table)
        except sqlite3.OperationalError as exc:
            if table == "research_events" and "no such table" in str(exc).lower():
                count, checksum = 0, hashlib.sha256(b"").hexdigest()
            else:
                raise RuntimeError(f"Cannot read SQLite {table}: {exc}") from exc
        stats[table] = {"count": count, "checksum": checksum}
    payload = {"schema_version": SCHEMA_VERSION, "tables": stats}
    encoded = canonical_json(payload).encode("utf-8")
    payload["fingerprint"] = hashlib.sha256(encoded).hexdigest()
    return payload


def target_stats(conn, table: str) -> tuple[int, str]:
    if table == "research_sessions":
        query = "SELECT session_id, owner_id, state_json, version, created_at, updated_at FROM research_sessions ORDER BY session_id"
    else:
        query = "SELECT event_id, session_id, version, event_type, payload_json, created_at FROM research_events ORDER BY event_id"
    count = 0
    digest = hashlib.sha256()
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur:
            digest.update(row_bytes(table, row))
            count += 1
    return count, digest.hexdigest()


def target_schema_ready(conn: Any) -> bool:
    """Return whether both research tables already exist; never creates objects."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('research_sessions','research_events')"
        )
        return int(cur.fetchone()[0]) == 2


def target_fingerprint(conn: Any) -> dict[str, Any]:
    stats = {}
    for table in TABLES:
        count, checksum = target_stats(conn, table)
        stats[table] = {"count": count, "checksum": checksum}
    payload = {"schema_version": SCHEMA_VERSION, "tables": stats}
    payload["fingerprint"] = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    return payload


def ensure_target_schema(conn: Any) -> None:
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


def ensure_migration_table(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS voicelab_sqlite_migrations (
                job_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                source_manifest JSONB NOT NULL,
                status TEXT NOT NULL,
                sessions_done BIGINT NOT NULL DEFAULT 0,
                events_done BIGINT NOT NULL DEFAULT 0,
                started_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL,
                completed_at DOUBLE PRECISION,
                error TEXT
            )
        """)
    conn.commit()


def load_job(conn: Any, job_id: str):
    with conn.cursor() as cur:
        cur.execute("SELECT job_id, source_path, source_fingerprint, source_manifest, status, sessions_done, events_done, started_at, updated_at, completed_at, error FROM voicelab_sqlite_migrations WHERE job_id=%s", (job_id,))
        return cur.fetchone()


def print_manifest(title: str, manifest: dict[str, Any]) -> None:
    print(f"\n{title}")
    for table in TABLES:
        item = manifest["tables"][table]
        print(f"  {table}: rows={item['count']} sha256={item['checksum']}")
    print(f"  fingerprint: {manifest['fingerprint']}")


def create_job(conn: Any, job_id: str, source_path: str, manifest: dict[str, Any]) -> None:
    now = time.time()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO voicelab_sqlite_migrations(job_id, source_path, source_fingerprint, source_manifest, status, started_at, updated_at) VALUES(%s,%s,%s,%s::jsonb,%s,%s,%s)",
            (job_id, source_path, manifest["fingerprint"], canonical_json(manifest), "running", now, now),
        )
    conn.commit()


def update_job(conn: Any, job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = time.time()
    assignments = ", ".join(f"{key}=%s" for key in fields)
    values = list(fields.values()) + [job_id]
    with conn.cursor() as cur:
        cur.execute(f"UPDATE voicelab_sqlite_migrations SET {assignments} WHERE job_id=%s", values)
    conn.commit()


def target_is_empty(conn: Any) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT (SELECT count(*) FROM research_sessions), (SELECT count(*) FROM research_events)")
        sessions, events = cur.fetchone()
    return sessions == 0 and events == 0


def fetch_existing_session(conn: Any, session_id: str):
    with conn.cursor() as cur:
        cur.execute("SELECT session_id, owner_id, state_json, version, created_at, updated_at FROM research_sessions WHERE session_id=%s", (session_id,))
        return cur.fetchone()


def fetch_existing_event(conn: Any, event_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT event_id, session_id, version, event_type, payload_json, created_at FROM research_events WHERE event_id=%s", (event_id,))
        return cur.fetchone()


def migrate_sessions(sqlite_conn: sqlite3.Connection, pg_conn: Any, job_id: str, batch_size: int, total: int) -> int:
    done = 0
    batch = []
    for row in source_rows(sqlite_conn, "research_sessions"):
        batch.append(row)
        if len(batch) >= batch_size:
            done += write_session_batch(pg_conn, batch)
            update_job(pg_conn, job_id, sessions_done=done)
            print(f"  sessions: {done}/{total}")
            batch.clear()
    if batch:
        done += write_session_batch(pg_conn, batch)
        update_job(pg_conn, job_id, sessions_done=done)
        print(f"  sessions: {done}/{total}")
    return done


def write_session_batch(conn: Any, rows: list[tuple[Any, ...]]) -> int:
    with conn.transaction():
        with conn.cursor() as cur:
            for row in rows:
                existing = fetch_existing_session(conn, row[0])
                if existing is not None:
                    if row_bytes("research_sessions", existing) != row_bytes("research_sessions", row):
                        raise RuntimeError(f"Target conflict for session_id={row[0]}")
                    continue
                state = row[2] if isinstance(row[2], dict) else json.loads(row[2])
                cur.execute(
                    "INSERT INTO research_sessions(session_id, owner_id, state_json, version, created_at, updated_at) VALUES(%s,%s,%s::jsonb,%s,%s,%s)",
                    (row[0], row[1], canonical_json(state), row[3], row[4], row[5]),
                )
    return len(rows)


def migrate_events(sqlite_conn: sqlite3.Connection, pg_conn: Any, job_id: str, batch_size: int, total: int) -> int:
    done = 0
    batch = []
    for row in source_rows(sqlite_conn, "research_events"):
        batch.append(row)
        if len(batch) >= batch_size:
            done += write_event_batch(pg_conn, batch)
            update_job(pg_conn, job_id, events_done=done)
            print(f"  events: {done}/{total}")
            batch.clear()
    if batch:
        done += write_event_batch(pg_conn, batch)
        update_job(pg_conn, job_id, events_done=done)
        print(f"  events: {done}/{total}")
    return done


def write_event_batch(conn: Any, rows: list[tuple[Any, ...]]) -> int:
    with conn.transaction():
        with conn.cursor() as cur:
            for row in rows:
                existing = fetch_existing_event(conn, int(row[0]))
                if existing is not None:
                    if row_bytes("research_events", existing) != row_bytes("research_events", row):
                        raise RuntimeError(f"Target conflict for event_id={row[0]}")
                    continue
                payload = row[4] if isinstance(row[4], dict) else json.loads(row[4])
                cur.execute(
                    "INSERT INTO research_events(event_id, session_id, version, event_type, payload_json, created_at) VALUES(%s,%s,%s,%s,%s::jsonb,%s)",
                    (int(row[0]), row[1], row[2], row[3], canonical_json(payload), row[5]),
                )
    return len(rows)


def reset_event_sequence(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(event_id), 0) FROM research_events")
        max_id = int(cur.fetchone()[0])
        cur.execute("SELECT setval(pg_get_serial_sequence('research_events','event_id'), GREATEST(%s, 1), %s > 0)", (max_id, max_id))
    conn.commit()


def validate(source: dict[str, Any], pg_conn: Any) -> dict[str, Any]:
    target = target_fingerprint(pg_conn)
    print_manifest("Source checksum", source)
    print_manifest("PostgreSQL checksum", target)
    if source["fingerprint"] != target["fingerprint"]:
        raise RuntimeError("Checksum validation FAILED: PostgreSQL does not exactly match the SQLite source.")
    print("\nChecksum validation: PASS")
    return target


def rollback(pg_conn: Any, job_id: str) -> None:
    job = load_job(pg_conn, job_id)
    if job is None:
        raise RuntimeError(f"Migration job not found: {job_id}")
    if job[4] != "completed":
        raise RuntimeError("Rollback is allowed only for a completed migration job.")
    manifest = job[3] if isinstance(job[3], dict) else json.loads(job[3])
    current = target_fingerprint(pg_conn)
    if current["fingerprint"] != manifest["fingerprint"]:
        raise RuntimeError(
            "Rollback refused: PostgreSQL changed after migration. Stop application writers and restore from a PostgreSQL backup instead."
        )
    with pg_conn.transaction():
        with pg_conn.cursor() as cur:
            cur.execute("DELETE FROM research_sessions")
            cur.execute("UPDATE voicelab_sqlite_migrations SET status='rolled_back', updated_at=%s, completed_at=NULL WHERE job_id=%s", (time.time(), job_id))
    print(f"Rollback complete for migration job {job_id}. PostgreSQL research data is empty.")


def run(args: argparse.Namespace) -> int:
    sqlite_path = Path(args.sqlite).expanduser().resolve()
    sqlite_conn = sqlite_connect(sqlite_path)
    source = source_fingerprint(sqlite_conn)
    print_manifest("SQLite source", source)

    pg_conn = postgres_store.connect()
    try:
        if args.dry_run:
            if target_schema_ready(pg_conn):
                target = target_fingerprint(pg_conn)
                print_manifest("Current PostgreSQL target", target)
                if not target_is_empty(pg_conn):
                    print("WARNING: target is not empty; a new migration job would refuse to start.")
            else:
                print("\nCurrent PostgreSQL target: research tables are not initialized yet.")
                print("A real migration will create the required tables transactionally before importing data.")
            print("\nDRY RUN: no PostgreSQL schema, migration metadata, or data rows were written.")
            return 0

        ensure_target_schema(pg_conn)
        ensure_migration_table(pg_conn)

        job_id = args.job_id or str(uuid4())
        job = load_job(pg_conn, job_id)
        if job is None:
            if not target_is_empty(pg_conn):
                raise RuntimeError("Refusing new migration: PostgreSQL research tables are not empty. Use an empty migration database.")
            create_job(pg_conn, job_id, str(sqlite_path), source)
            print(f"\nCreated migration job: {job_id}")
        else:
            stored_manifest = job[3] if isinstance(job[3], dict) else json.loads(job[3])
            if stored_manifest["fingerprint"] != source["fingerprint"]:
                raise RuntimeError("SQLite source fingerprint changed since this migration job started; refusing to resume.")
            if job[4] == "completed":
                print(f"Migration job {job_id} is already completed; validating only.")
                validate(source, pg_conn)
                return 0
            if job[4] == "rolled_back":
                raise RuntimeError("Migration job was rolled back; start a new job ID.")
            print(f"Resuming migration job: {job_id}")

        sessions_total = source["tables"]["research_sessions"]["count"]
        events_total = source["tables"]["research_events"]["count"]
        migrate_sessions(sqlite_conn, pg_conn, job_id, args.batch_size, sessions_total)
        migrate_events(sqlite_conn, pg_conn, job_id, args.batch_size, events_total)
        reset_event_sequence(pg_conn)
        validate(source, pg_conn)
        update_job(pg_conn, job_id, status="completed", completed_at=time.time(), error=None)
        print(f"\nMigration COMPLETE. Job ID: {job_id}")
        print("Safe cutover: stop SQLite writers, point VOICELAB_DATABASE_URL at this PostgreSQL database, then start VoiceLab.")
        return 0
    except Exception as exc:
        try:
            if not args.dry_run and 'job_id' in locals():
                update_job(pg_conn, job_id, status="failed", error=str(exc))
        except Exception:
            pass
        print(f"\nMigration FAILED: {exc}", file=sys.stderr)
        print("Resume: rerun the same command with the same --job-id after fixing the cause.", file=sys.stderr)
        return 2
    finally:
        sqlite_conn.close()
        pg_conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Production-safe, resumable SQLite -> PostgreSQL migration for VoiceLab")
    parser.add_argument("--sqlite", default=os.getenv("VOICELAB_STATE_DB", "voicelab_state.db"), help="SQLite source database")
    parser.add_argument("--job-id", help="Stable migration ID; required to resume an interrupted job")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true", help="Inspect source and target without migrating rows")
    parser.add_argument("--rollback", action="store_true", help="Rollback a completed migration job after strict checksum safety checks")
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 10000:
        parser.error("--batch-size must be between 1 and 10000")
    if args.rollback:
        if not args.job_id:
            parser.error("--rollback requires --job-id")
        pg_conn = postgres_store.connect()
        try:
            ensure_target_schema(pg_conn)
            ensure_migration_table(pg_conn)
            rollback(pg_conn, args.job_id)
            return 0
        finally:
            pg_conn.close()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
