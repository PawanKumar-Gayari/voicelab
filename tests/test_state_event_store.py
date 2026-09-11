import json
import sqlite3
import threading

import app.agent.state as state
from app.agent.state import create_session, get_session, session_events


def test_event_store_versions_and_replay(monkeypatch, tmp_path):
    state.DATABASE_PATH = tmp_path / "state.db"
    session = create_session(owner_id="u1")
    session.append_memory({"kind": "user", "text": "Analyze this molecule"})
    session.update_molecule_data({"id": "BF3", "formula": "BF3"})

    events = session_events(session.session_id)
    assert len(events) >= 2
    assert [e["version"] for e in events] == sorted(e["version"] for e in events)
    assert len({e["version"] for e in events}) == len(events)
    assert get_session(session.session_id).molecule_data["id"] == "BF3"


def test_concurrent_memory_appends_are_not_lost(monkeypatch, tmp_path):
    state.DATABASE_PATH = tmp_path / "state.db"
    session = create_session(owner_id="u1")
    workers = [get_session(session.session_id) for _ in range(8)]

    def append(worker, i):
        worker.append_memory({"kind": "concurrent", "i": i})

    threads = [threading.Thread(target=append, args=(w, i)) for i, w in enumerate(workers)]
    for t in threads: t.start()
    for t in threads: t.join()

    events = get_session(session.session_id).memory
    values = {item["i"] for item in events if item.get("kind") == "concurrent"}
    assert values == set(range(8))


def test_legacy_snapshot_schema_migrates(monkeypatch, tmp_path):
    db = tmp_path / "legacy.db"
    state.DATABASE_PATH = db
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE research_sessions (session_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
    con.execute("INSERT INTO research_sessions VALUES (?, ?)", ("legacy", json.dumps({"session_id": "legacy", "owner_id": "u1", "molecule": "BF3"})))
    con.commit(); con.close()

    loaded = get_session("legacy")
    assert loaded is not None
    assert loaded.molecule == "BF3"
    loaded.append_memory({"kind": "migration"})
    assert session_events("legacy")
