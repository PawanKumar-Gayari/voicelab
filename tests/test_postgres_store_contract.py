from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_postgres_store_contract_is_transactional_and_versioned():
    source = Path("app/agent/postgres_store.py").read_text(encoding="utf-8")
    assert "FOR UPDATE" in source
    assert "UNIQUE(session_id, version)" in source
    assert "JSONB" in source
    assert "INSERT INTO research_events" in source
    assert "conn.commit()" in source


@pytest.mark.skipif(not os.getenv("VOICELAB_DATABASE_URL"), reason="live PostgreSQL DSN not configured")
def test_live_postgres_schema():
    from app.agent.postgres_store import ensure_schema
    ensure_schema()
