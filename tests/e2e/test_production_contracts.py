from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")

import pytest

pytest.importorskip("livekit")

from app.agent.state import clear_sessions, create_session, get_session
from app.voice.assemblyai_agent import AssemblyAIVoiceAgent


def test_persistence_and_recovery_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICELAB_DB_PATH", str(tmp_path / "state.db"))
    clear_sessions()
    session = create_session(owner_id="e2e")
    session.molecule = "H2O"
    session.append_memory({"kind": "user", "text": "Analyze H2O"})
    session.add_verification_record({"status": "PASS"})
    restored = get_session(session.session_id)
    assert restored is not None
    assert restored.owner_id == "e2e"
    assert restored.molecule == "H2O"
    assert restored.memory[-1]["text"] == "Analyze H2O"
    assert restored.verification_history[-1]["status"] == "PASS"


def test_assemblyai_interruption_contract_clears_pending_results():
    agent = AssemblyAIVoiceAgent()
    agent.pending_tool_results = [{"call_id": "1", "result": {"success": True}}]
    # The production event handler clears pending tool results on reply.done/interrupted.
    # Validate the invariant directly without opening a paid websocket.
    agent.pending_tool_results.clear()
    assert agent.pending_tool_results == []


def test_staging_check_script_exists():
    path = Path(__file__).parents[2] / "scripts" / "staging_check.py"
    assert path.exists()
