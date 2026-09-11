"""
Shared research session state for VoiceLab.

The scientific research state is persisted in a local SQLite database so
the FastAPI process and the LiveKit Agent process can access the same
session.

This module contains no AI logic, voice logic, frontend logic, or
molecule-specific mathematical calculations.
"""

from __future__ import annotations

import json
import copy
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


# ---------------------------------------------------------------------------
# Shared SQLite database
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_default_db_path = (
    "/app/data/voicelab_state.db"
    if Path("/app/data").is_dir()
    else str(PROJECT_ROOT / "voicelab_state.db")
)

# Backward-compatible public path used by older integrations/tests.
# Runtime environment variables still take precedence when configured.
DATABASE_PATH = Path(_default_db_path)

def _database_config() -> tuple[str, str, Path]:
    """Resolve database configuration from the current process environment."""
    database_url = os.getenv(
        "VOICELAB_DATABASE_URL",
        os.getenv("DATABASE_URL", ""),
    ).strip()
    backend = (
        "postgres"
        if database_url.startswith(("postgres://", "postgresql://"))
        else "sqlite"
    )
    database_path = Path(
        os.getenv(
            "VOICELAB_STATE_DB",
            os.getenv("VOICELAB_DB_PATH", str(DATABASE_PATH)),
        )
    )
    return database_url, backend, database_path


def _connect() -> sqlite3.Connection:
    """Open the shared SQLite store with production-safe concurrency settings."""
    _, backend, database_path = _database_config()
    if backend != "sqlite":
        raise RuntimeError("SQLite connection requested while PostgreSQL is configured.")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_sessions (
            session_id TEXT PRIMARY KEY,
            owner_id TEXT,
            state_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY(session_id) REFERENCES research_sessions(session_id) ON DELETE CASCADE,
            UNIQUE(session_id, version)
        )
        """
    )
    # Backward-compatible migration from the old two-column snapshot table.
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(research_sessions)").fetchall()}
    if "owner_id" not in columns:
        connection.execute("ALTER TABLE research_sessions ADD COLUMN owner_id TEXT")
    if "version" not in columns:
        connection.execute("ALTER TABLE research_sessions ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in columns:
        connection.execute("ALTER TABLE research_sessions ADD COLUMN created_at REAL NOT NULL DEFAULT 0")
        connection.execute("UPDATE research_sessions SET created_at = ? WHERE created_at = 0", (time.time(),))
    if "updated_at" not in columns:
        connection.execute("ALTER TABLE research_sessions ADD COLUMN updated_at REAL NOT NULL DEFAULT 0")
        connection.execute("UPDATE research_sessions SET updated_at = ? WHERE updated_at = 0", (time.time(),))

    connection.execute("CREATE INDEX IF NOT EXISTS idx_research_events_session ON research_events(session_id, event_id)")
    return connection


def _json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _public_state(session: "ResearchSession") -> dict[str, Any]:
    return copy.deepcopy({
        "session_id": session.session_id,
        "owner_id": session.owner_id,
        "molecule": session.molecule,
        "point_group": session.point_group,
        "molecule_data": session.molecule_data,
        "operations": session.operations,
        "matrices": session.matrices,
        "representation": session.representation,
        "characters": session.characters,
        "verification": session.verification,
        "group_theory": session.group_theory,
        "vibrational_analysis": session.vibrational_analysis,
        "report": session.report,
        "memory": session.memory,
        "verification_history": session.verification_history,
    })


def _load_row(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT session_id, owner_id, state_json, version FROM research_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()


def _session_from_state(state: dict[str, Any], version: int = 1) -> "ResearchSession":
    session = ResearchSession(
        session_id=state["session_id"], owner_id=state.get("owner_id"),
        molecule=state.get("molecule"), point_group=state.get("point_group"),
        molecule_data=state.get("molecule_data", {}), operations=state.get("operations", []),
        matrices=state.get("matrices", {}), representation=state.get("representation", {}),
        characters=state.get("characters", {}), verification=state.get("verification", {}),
        group_theory=state.get("group_theory", {}), report=state.get("report"),
        vibrational_analysis=state.get("vibrational_analysis"),
        memory=state.get("memory", []), verification_history=state.get("verification_history", []),
    )
    session._version = int(version)
    session._baseline = copy.deepcopy(_public_state(session))
    return session


def _load_session(session_id: str) -> "ResearchSession | None":
    _, database_backend, _ = _database_config()
    if database_backend == "postgres":
        from app.agent import postgres_store
        row = postgres_store.load_session_row(session_id)
        if row is None:
            return None
        state = row[2] if isinstance(row[2], dict) else json.loads(row[2])
        return _session_from_state(state, row[3])
    with _connect() as connection:
        row = _load_row(connection, session_id)
        if row is None:
            return None
        return _session_from_state(json.loads(row["state_json"]), row["version"])


def _merge_changes(latest: dict[str, Any], baseline: dict[str, Any], desired: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    merged = dict(latest)
    changed: list[str] = []
    for key in desired:
        if key == "session_id":
            continue
        if desired.get(key) != baseline.get(key):
            if key in ("memory", "verification_history") and isinstance(desired.get(key), list) and isinstance(baseline.get(key), list):
                # Merge append-only lists by stable JSON identity so concurrent workers never lose events.
                base_items = [json.dumps(x, sort_keys=True, default=_json_default) for x in baseline[key]]
                additions = [x for x in desired[key] if json.dumps(x, sort_keys=True, default=_json_default) not in base_items]
                current = list(latest.get(key) or [])
                current_keys = {json.dumps(x, sort_keys=True, default=_json_default) for x in current}
                current.extend(x for x in additions if json.dumps(x, sort_keys=True, default=_json_default) not in current_keys)
                merged[key] = current[-250:] if key == "memory" else current[-50:]
            else:
                merged[key] = desired.get(key)
            changed.append(key)
    return merged, changed


def _persist_session(session: "ResearchSession", event_type: str = "state_update") -> None:
    _, database_backend, _ = _database_config()
    if database_backend == "postgres":
        from app.agent import postgres_store
        desired = _public_state(session)
        merged, new_version = postgres_store.persist(
            session, desired, session._baseline or {}, event_type, _merge_changes, _json_default
        )
        session._apply_public_state(merged)
        session._version = new_version
        session._baseline = copy.deepcopy(merged)
        return

    """Atomically merge a session mutation, bump its version, and append an audit event.

    This removes read-modify-write races between FastAPI and the LiveKit worker.
    Concurrent memory/replay events are merged append-only; scalar fields use
    optimistic last-writer-wins semantics inside the serialized SQLite transaction.
    """
    desired = _public_state(session)
    baseline = session._baseline or {}
    for attempt in range(4):
        try:
            with _connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = _load_row(connection, session.session_id)
                now = time.time()
                if row is None:
                    new_version = 1
                    merged = desired
                    connection.execute(
                        "INSERT INTO research_sessions(session_id, owner_id, state_json, version, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                        (session.session_id, merged.get("owner_id"), json.dumps(merged, default=_json_default), new_version, now, now),
                    )
                else:
                    latest = json.loads(row["state_json"])
                    merged, changed = _merge_changes(latest, baseline, desired)
                    if not changed:
                        connection.execute("COMMIT")
                        session._version = int(row["version"])
                        session._baseline = latest
                        return
                    new_version = int(row["version"]) + 1
                    cursor = connection.execute(
                        "UPDATE research_sessions SET owner_id=?, state_json=?, version=?, updated_at=? WHERE session_id=? AND version=?",
                        (merged.get("owner_id"), json.dumps(merged, default=_json_default), new_version, now, session.session_id, int(row["version"])),
                    )
                    if cursor.rowcount != 1:
                        connection.execute("ROLLBACK")
                        continue
                event_payload = {"changed": changed if row is not None else list(desired.keys()), "state": merged}
                connection.execute(
                    "INSERT INTO research_events(session_id, version, event_type, payload_json, created_at) VALUES(?,?,?,?,?)",
                    (session.session_id, new_version, event_type, json.dumps(event_payload, default=_json_default), now),
                )
                connection.execute("COMMIT")
                session._apply_public_state(merged)
                session._version = new_version
                session._baseline = copy.deepcopy(merged)
                return
        except sqlite3.OperationalError as exc:
            if attempt == 3:
                raise
            time.sleep(0.05 * (attempt + 1))


def session_events(session_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Return the append-only event stream for a session."""
    _, database_backend, _ = _database_config()
    if database_backend == "postgres":
        from app.agent import postgres_store
        return postgres_store.events(session_id, limit)
    with _connect() as connection:
        rows = connection.execute(
            "SELECT event_id, version, event_type, payload_json, created_at FROM research_events WHERE session_id=? ORDER BY event_id ASC LIMIT ?",
            (session_id, max(1, min(int(limit), 10000))),
        ).fetchall()
    return [{"event_id": r["event_id"], "version": r["version"], "event_type": r["event_type"], "payload": json.loads(r["payload_json"]), "created_at": r["created_at"]} for r in rows]


# ---------------------------------------------------------------------------
# Research session
# ---------------------------------------------------------------------------


@dataclass
class ResearchSession:
    """
    Current state of one VoiceLab research session.
    """

    session_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    owner_id: str | None = None

    molecule: str | None = None
    point_group: str | None = None

    # Generic molecule payload supplied by the scientific registry.
    # This keeps geometry/metadata available to the browser without
    # introducing molecule-specific frontend logic.
    molecule_data: dict[str, Any] = field(default_factory=dict)

    operations: list[dict[str, Any]] = field(
        default_factory=list
    )

    matrices: dict[str, Any] = field(
        default_factory=dict
    )

    representation: dict[str, Any] = field(
        default_factory=dict
    )

    characters: dict[str, Any] = field(
        default_factory=dict
    )

    verification: dict[str, Any] = field(
        default_factory=dict
    )

    group_theory: dict[str, Any] = field(
        default_factory=dict
    )

    vibrational_analysis: dict[str, Any] | None = None

    report: str | None = None

    # Durable agent memory / replay timeline. Entries are compact JSON-safe
    # records so voice, typed commands, vision, and tool actions share one
    # chronological history across FastAPI and LiveKit processes.
    memory: list[dict[str, Any]] = field(default_factory=list)
    verification_history: list[dict[str, Any]] = field(default_factory=list)

    _version: int = field(default=0, init=False, repr=False, compare=False)
    _baseline: dict[str, Any] = field(default_factory=dict, init=False, repr=False, compare=False)

    def _apply_public_state(self, state: dict[str, Any]) -> None:
        for key, value in state.items():
            if key != "session_id" and hasattr(self, key):
                setattr(self, key, value)

    def _persist(self, event_type: str = "state_update") -> None:
        _persist_session(self, event_type=event_type)

    def _refresh(self) -> None:
        stored = _load_session(self.session_id)
        if stored is not None:
            self._apply_public_state(_public_state(stored))
            self._version = stored._version
            self._baseline = stored._baseline

    def update_symmetry(
        self,
        molecule: str,
        point_group: str,
        operations: list[dict[str, Any]],
    ) -> None:
        """
        Store the symmetry-analysis result.
        """
        self.molecule = molecule
        self.point_group = point_group
        self.operations = operations

        self._persist()

    def update_molecule_data(
        self,
        molecule_data: dict[str, Any],
    ) -> None:
        """Store the generic registry molecule payload for the UI."""
        self.molecule_data = molecule_data if isinstance(molecule_data, dict) else {}
        self._persist()

    def update_matrices(
        self,
        matrices: dict[str, Any],
    ) -> None:
        """
        Store Cartesian transformation matrices.
        """
        self.matrices = matrices

        self._persist()

    def update_representation(
        self,
        representation: dict[str, Any],
    ) -> None:
        """
        Store representation matrices.
        """
        self.representation = representation

        if isinstance(representation, dict):
            characters = representation.get("characters")

            if isinstance(characters, dict):
                self.characters = characters

        self._persist()

    def update_characters(
        self,
        characters: dict[str, Any],
    ) -> None:
        """
        Store representation characters.
        """
        self.characters = characters

        self._persist()

    def update_verification(
        self,
        verification: dict[str, Any],
    ) -> None:
        """
        Store verification result.
        """
        self.verification = verification

        self._persist()

    def update_reduction(
        self,
        group_theory: dict[str, Any],
    ) -> None:
        """
        Store point-group character-table and irreducible-representation
        reduction data.
        """
        self.group_theory = group_theory

        self._persist()

    def update_vibrational_analysis(
        self,
        vibrational_analysis: dict[str, Any] | None,
    ) -> None:
        """Store the verified vibrational, IR, and Raman analysis."""
        self.vibrational_analysis = (
            vibrational_analysis
            if isinstance(vibrational_analysis, dict)
            else None
        )
        self._persist()

    def append_memory(self, event: dict[str, Any], limit: int = 250) -> None:
        """Append a compact replayable event to durable agent memory."""
        if not isinstance(event, dict):
            return
        item = dict(event)
        self.memory.append(item)
        self.memory = self.memory[-max(1, int(limit)):]
        self._persist(event_type="memory_append")

    def add_verification_record(self, record: dict[str, Any], limit: int = 50) -> None:
        """Persist an auditable verification record."""
        if not isinstance(record, dict):
            return
        self.verification_history.append(dict(record))
        self.verification_history = self.verification_history[-max(1, int(limit)):]
        self._persist(event_type="verification_append")

    def update_report(
        self,
        report: str,
    ) -> None:
        """
        Store the generated report.
        """
        self.report = report

        self._persist()

    def is_verified(self) -> bool:
        """
        Return True only when verification explicitly reports PASS.
        """
        if not isinstance(self.verification, dict):
            return False

        return self.verification.get("status") == "PASS"

    def reset_calculation(self) -> None:
        """
        Clear calculated data while keeping molecule/symmetry information.
        """
        self.matrices = {}
        self.representation = {}
        self.characters = {}
        self.verification = {}
        self.group_theory = {}
        self.vibrational_analysis = None
        self.report = None
        self.verification_history = []

        self._persist()

    def reset(self) -> None:
        """
        Reset the complete research session.
        """
        self.molecule = None
        self.point_group = None
        self.molecule_data = {}
        self.operations = []
        self.matrices = {}
        self.representation = {}
        self.characters = {}
        self.verification = {}
        self.group_theory = {}
        self.vibrational_analysis = None
        self.report = None
        self.memory = []
        self.verification_history = []

        self._persist()

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the session into the shared application data contract.

        Always refresh from SQLite first so another process, such as the
        LiveKit worker, can update the state and the FastAPI process will
        immediately see those changes.
        """
        self._refresh()

        return _public_state(self) | {"version": self._version}


# ---------------------------------------------------------------------------
# Local compatibility cache
# ---------------------------------------------------------------------------

# Kept for compatibility with existing code/tests.
# SQLite remains the actual source of truth.
_sessions: dict[str, ResearchSession] = {}


# ---------------------------------------------------------------------------
# Session store API
# ---------------------------------------------------------------------------


def create_session(owner_id: str | None = None) -> ResearchSession:
    """
    Create and persist a new research session.
    """
    session = ResearchSession(owner_id=owner_id)

    _sessions[session.session_id] = session

    _persist_session(session, event_type="session_created")

    return session


def get_session(
    session_id: str,
) -> ResearchSession | None:
    """
    Retrieve a session from the shared SQLite database.

    Returns None when the session does not exist.
    """
    session = _load_session(session_id)

    if session is not None:
        _sessions[session.session_id] = session

    return session


def require_session(
    session_id: str,
) -> ResearchSession:
    """
    Retrieve a session or raise a clear error.
    """
    session = get_session(session_id)

    if session is None:
        raise KeyError(
            f"Research session not found: {session_id}"
        )

    return session


def delete_session(
    session_id: str,
) -> bool:
    """
    Delete a session from the configured store and the local compatibility cache.
    """
    _, database_backend, _ = _database_config()
    if database_backend == "postgres":
        from app.agent import postgres_store
        deleted = postgres_store.delete(session_id)
        _sessions.pop(session_id, None)
        return deleted
    with _connect() as connection:
        cursor = connection.execute(
            """
            DELETE FROM research_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        )

        connection.commit()

        deleted = cursor.rowcount > 0

    _sessions.pop(session_id, None)

    return deleted


def clear_sessions() -> None:
    """
    Clear all research sessions.

    Primarily useful for testing and development.
    """
    _, database_backend, _ = _database_config()
    if database_backend == "postgres":
        from app.agent import postgres_store
        postgres_store.clear()
        _sessions.clear()
        return
    with _connect() as connection:
        connection.execute(
            """
            DELETE FROM research_sessions
            """
        )

        connection.commit()

    _sessions.clear()
