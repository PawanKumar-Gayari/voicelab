"""Static + optional live PostgreSQL store verification.

Usage:
  python scripts/verify_postgres_store.py
  python scripts/verify_postgres_store.py --live
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def static_checks() -> None:
    from app.agent import state, postgres_store
    assert state.DATABASE_BACKEND in {"sqlite", "postgres"}
    assert "FOR UPDATE" in open("app/agent/postgres_store.py", encoding="utf-8").read()
    assert "UNIQUE(session_id, version)" in open("app/agent/postgres_store.py", encoding="utf-8").read()
    assert "JSONB" in open("app/agent/postgres_store.py", encoding="utf-8").read()
    print("PostgreSQL store static contract: PASS")


def live_checks() -> None:
    if not os.getenv("VOICELAB_DATABASE_URL"):
        raise SystemExit("VOICELAB_DATABASE_URL is required for --live")
    from app.agent import postgres_store
    postgres_store.ensure_schema()
    print("PostgreSQL schema connectivity: PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    static_checks()
    if args.live:
        live_checks()
