from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/migrate_sqlite_to_postgres.py")


def test_migration_command_has_safety_contract():
    source = SCRIPT.read_text(encoding="utf-8")
    required = [
        "--dry-run",
        "--job-id",
        "--rollback",
        "source_fingerprint",
        "SHA-256",
        "voicelab_sqlite_migrations",
        "research_sessions",
        "research_events",
        "Checksum validation FAILED",
        "Target conflict",
        "source fingerprint changed",
        "target_is_empty",
        "setval(pg_get_serial_sequence",
    ]
    for token in required:
        assert token in source


def test_migration_uses_explicit_event_ids_and_transactional_batches():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "INSERT INTO research_events(event_id" in source
    assert "with conn.transaction():" in source
    assert "update_job(pg_conn, job_id, sessions_done=done)" in source
    assert "update_job(pg_conn, job_id, events_done=done)" in source
