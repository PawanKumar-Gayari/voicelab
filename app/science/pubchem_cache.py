"""Small SQLite cache for validated external molecular geometries.

The cache stores only successful, fully validated records. It never becomes
the scientific authority: callers must still be able to re-verify a cached
record when policy requires it.
"""
from __future__ import annotations
import json
import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS pubchem_geometry_cache (
    cache_key TEXT PRIMARY KEY,
    cid INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

def _connect(path):
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn

def get_cached(path, cache_key):
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT payload_json FROM pubchem_geometry_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()
    return json.loads(row[0]) if row else None

def put_cached(path, cache_key, cid, payload: dict[str, Any]):
    with _connect(path) as conn:
        conn.execute(
            """INSERT INTO pubchem_geometry_cache(cache_key,cid,payload_json)
               VALUES(?,?,?)
               ON CONFLICT(cache_key) DO UPDATE SET
                 cid=excluded.cid,payload_json=excluded.payload_json""",
            (cache_key, cid, json.dumps(payload, sort_keys=True)),
        )
        conn.commit()
