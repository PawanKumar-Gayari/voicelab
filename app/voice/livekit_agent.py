"""VoiceLab LiveKit + AssemblyAI Voice Agent bridge.

Architecture:

    Browser
        |
        | WebRTC
        v
    LiveKit
        |
        | PCM16 24 kHz mono
        v
    AssemblyAI Voice Agent API
        |
        +-- STT
        +-- LLM
        +-- TTS
        +-- turn detection
        +-- barge-in
        +-- tool calling
        |
        v
    VoiceLab deterministic science tools

LiveKit is transport only.
AssemblyAI owns the complete voice-agent pipeline.

The existing VoiceLab science functions are intentionally unchanged.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

import websockets
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AgentServer, JobContext, cli

from app.agent.state import ResearchSession, get_session
from app.agent.system_prompt import get_system_prompt
from app.tools.full_analysis import analyze_molecule
from app.tools.representation import calculate_representation
from app.tools.symmetry import analyze_symmetry
from app.tools.verification import verify_representation
from app.tools.operation_test import run_molecule_operation
from app.science.molecule_registry import get_molecule


load_dotenv()

logger = logging.getLogger("voicelab-livekit")

server = AgentServer()

ASSEMBLYAI_WS_URL = "wss://agents.assemblyai.com/v1/ws"

LIVEKIT_ROOM_PREFIX = "voicelab-"

AUDIO_SAMPLE_RATE = 24_000
AUDIO_CHANNELS = 1

AGENT_IDENTITY = "voicelab-agent"
AGENT_TRACK_NAME = "voicelab-voice"


KEYTERMS = [
    "VoiceLab",
    "AssemblyAI",
    "LiveKit",
    "BF3",
    "B F 3",
    "boron trifluoride",
    "CH4",
    "C H 4",
    "methane",
    "H2O",
    "H 2 O",
    "water",
    "NH3",
    "N H 3",
    "ammonia",
    "D3h",
    "C3v",
    "Td",
    "symmetry",
    "point group",
    "symmetry operation",
    "transformation matrix",
    "Cartesian representation",
    "representation",
    "characters",
    "character",
    "irreducible representation",
    "basis",
    "verification",
]


INSTRUCTIONS = get_system_prompt() + """

VOICE RUNTIME RULES:

- You are VoiceLab, a scientific molecular-symmetry research assistant.
- AssemblyAI handles speech recognition, reasoning, turn detection, and speech output.
- Use the VoiceLab deterministic Python tools for all mathematical calculations.
- NEVER invent matrices, operations, characters, point groups, representations, or
  verification results.
- NEVER calculate scientific numerical results mentally when a VoiceLab tool exists.
- Prefer full_analysis when the user asks to start or complete a molecule analysis.
- When the user asks for vibrational modes, vibrations, normal modes, IR activity,
  Raman activity, or vibrational analysis, use full_analysis with
  include_vibrations=true.
- When the user asks only for ordinary molecular symmetry analysis and does not
  request vibrations, use full_analysis with include_vibrations=false or omit it.
- Use analyze_symmetry when the user specifically asks for symmetry operations or
  point-group analysis.
- Use calculate_representation when the user specifically asks for the Cartesian
  representation or characters.
- Use verify_representation when the user asks to verify an existing result.
- A result may only be described as VERIFIED when the verification tool returns PASS.
- Keep spoken responses concise because detailed mathematical state is displayed
  in the VoiceLab workspace.
- When a calculation finishes, briefly state what was actually computed.
- If a requested molecule is not registered, say so rather than inventing data.
"""


def _session_id_from_room(room_name: str) -> str:
    """Extract the VoiceLab research-session ID from the LiveKit room name."""
    if not room_name.startswith(LIVEKIT_ROOM_PREFIX):
        raise ValueError(
            f"Invalid VoiceLab LiveKit room {room_name!r}. "
            f"Expected prefix {LIVEKIT_ROOM_PREFIX!r}."
        )

    session_id = room_name[len(LIVEKIT_ROOM_PREFIX):].strip()

    if not session_id:
        raise ValueError(
            "LiveKit room does not contain a VoiceLab session ID."
        )

    return session_id


def _state_for_room(room_name: str) -> ResearchSession:
    """Return the shared ResearchSession created by FastAPI."""
    session_id = _session_id_from_room(room_name)

    research = get_session(session_id)

    if research is None:
        raise RuntimeError(
            f"VoiceLab research session {session_id!r} was not found. "
            "Create the session through POST /api/sessions before joining LiveKit."
        )

    return research


def _json_safe(value: Any) -> Any:
    """Convert common NumPy/Python values into JSON-safe values."""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass

    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass

    return str(value)


def _tool_definition(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    """Build an AssemblyAI Voice Agent API function definition."""
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


SCIENCE_TOOLS = [
    _tool_definition(
        name="full_analysis",
        description=(
            "Run the complete deterministic VoiceLab molecular symmetry "
            "analysis for a registered molecule. Use this when the user asks "
            "to start, perform, complete, or fully analyze a molecule."
        ),
        properties={
            "molecule": {
                "type": "string",
                "description": (
                    "Molecule identifier, name, or formula. "
                    "Examples: BF3, H2O."
                ),
            },
            "basis": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional Cartesian basis, normally ['x', 'y', 'z']."
                ),
            },
            "include_vibrations": {
                "type": "boolean",
                "description": (
                    "Set true for vibrational modes, normal modes, IR activity, "
                    "Raman activity, or vibrational analysis. Set false for "
                    "ordinary molecular symmetry analysis."
                ),
            },
        },
        required=["molecule", "include_vibrations"],
    ),
    _tool_definition(
        name="generate_transformation_matrices",
        description=(
            "Generate the molecule's Cartesian transformation matrices for its "
            "registered symmetry operations. Use this when the user explicitly "
            "asks for transformation matrices or Cartesian transformation matrices."
        ),
        properties={
            "molecule": {
                "type": "string",
                "description": "Molecule identifier, name, or formula.",
            },
        },
        required=["molecule"],
    ),
    _tool_definition(
        name="analyze_symmetry",
        description=(
            "Determine the registered molecule's symmetry operations and "
            "point group using VoiceLab's deterministic symmetry engine."
        ),
        properties={
            "molecule": {
                "type": "string",
                "description": "Molecule identifier, name, or formula.",
            },
        },
        required=["molecule"],
    ),
    _tool_definition(
        name="calculate_representation",
        description=(
            "Calculate Cartesian representation matrices and characters "
            "from the supplied molecule operations."
        ),
        properties={
            "molecule": {
                "type": "string",
                "description": "Molecule identifier, name, or formula.",
            },
            "basis": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Cartesian basis, normally ['x', 'y', 'z']."
                ),
            },
            "operations": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "The symmetry operations returned by analyze_symmetry "
                    "or full_analysis."
                ),
            },
        },
        required=["molecule", "basis", "operations"],
    ),
    _tool_definition(
        name="control_molecule_viewer",
        description=(
            "Control the currently displayed molecule in the browser. Use this "
            "when the researcher asks to rotate, turn, zoom, or reset the molecular "
            "viewer (for example: rotate left, rotate right, zoom in, zoom out, "
            "reset the molecule view). This changes only the visual camera/view "
            "and does not change scientific data."
        ),
        properties={
            "action": {
                "type": "string",
                "enum": [
                    "rotate-left",
                    "rotate-right",
                    "zoom-in",
                    "zoom-out",
                    "show-atom-labels",
                    "hide-atom-labels",
                    "show-element-names",
                    "hide-element-names",
                    "show-c3-axis",
                    "show-c2-axes",
                    "show-sigma-h",
                    "clear-highlights",
                    "reset",
                ],
                "description": "Viewer action to perform.",
            },
        },
        required=["action"],
    ),
    _tool_definition(
        name="test_symmetry_operation",
        description=(
            "Actually construct and test a candidate Cartesian symmetry operation "
            "against the current molecule coordinates. Use this for requests like "
            "Test C4; never answer a negative symmetry claim without running the test."
        ),
        properties={
            "molecule": {"type": "string", "description": "Molecule identifier, name, or formula."},
            "operation": {
                "type": "object",
                "description": "Candidate transformation. Example C4 about z: {type:'rotation', axis:[0,0,1], angle_deg:90}.",
                "properties": {
                    "type": {"type": "string", "enum": ["identity", "rotation", "reflection", "inversion", "improper_rotation"]},
                    "axis": {"type": "array", "items": {"type": "number"}},
                    "plane_normal": {"type": "array", "items": {"type": "number"}},
                    "angle_deg": {"type": "number"},
                    "id": {"type": "string"},
                    "symbol": {"type": "string"},
                },
                "required": ["type"],
            },
        },
        required=["molecule", "operation"],
    ),
    _tool_definition(
        name="verify_representation",
        description=(
            "Independently verify representation matrices and characters. "
            "Only a PASS result should be described as verified."
        ),
        properties={
            "molecule": {
                "type": "string",
                "description": "Molecule identifier, name, or formula.",
            },
            "operations": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Symmetry operations to verify.",
            },
            "representation_matrices": {
                "type": "object",
                "description": (
                    "Representation matrices produced by the representation tool."
                ),
            },
            "characters": {
                "type": "object",
                "description": (
                    "Characters produced by the representation tool."
                ),
            },
        },
        required=[
            "molecule",
            "operations",
            "representation_matrices",
            "characters",
        ],
    ),
]


def _sync_registry_molecule_data(
    research: ResearchSession,
    result: dict[str, Any],
    requested_molecule: str | None = None,
) -> None:
    """Synchronize generic registry geometry/metadata into shared UI state.

    Different scientific tools expose molecule data at slightly different
    nesting levels. The browser should not need to know those shapes, so the
    voice bridge normalizes them here and falls back to the registry when a
    tool only returns an identifier plus coordinates.
    """
    if not isinstance(result, dict) or not result.get("success"):
        return

    data = result.get("data")
    if not isinstance(data, dict):
        data = {}

    molecule = data.get("molecule")
    if not isinstance(molecule, dict):
        molecule = {}

    molecule_id = (
        molecule.get("id")
        or data.get("molecule")
        or requested_molecule
    )

    # Prefer the scientific tool's payload. If that payload is minimal,
    # resolve the authoritative geometry/metadata from the registry.
    registry_data: dict[str, Any] = {}
    if molecule_id:
        try:
            definition = get_molecule(str(molecule_id))
            registry_data = {
                "id": definition.molecule_id,
                "name": definition.name,
                "formula": definition.formula,
                "point_group": definition.point_group,
                "coordinates": definition.coordinates,
                "bonds": getattr(definition, "bonds", []),
            }
        except Exception:
            registry_data = {}

    coordinates = (
        molecule.get("coordinates")
        or data.get("coordinates")
        or registry_data.get("coordinates")
        or {}
    )

    if not coordinates:
        return

    payload = {
        "id": molecule.get("id") or registry_data.get("id") or molecule_id,
        "name": molecule.get("name") or registry_data.get("name") or molecule_id,
        "formula": molecule.get("formula") or registry_data.get("formula"),
        "point_group": (
            molecule.get("point_group")
            or data.get("point_group")
            or registry_data.get("point_group")
        ),
        "coordinates": coordinates,
        "bonds": molecule.get("bonds") or data.get("bonds") or registry_data.get("bonds", []),
    }

    research.update_molecule_data(payload)


def _update_research_from_full_analysis(
    research: ResearchSession,
    result: dict[str, Any],
) -> None:
    """Synchronize full-analysis results into shared VoiceLab state."""
    if not result.get("success"):
        return

    data = result.get("data", {})

    molecule = data.get("molecule", {})
    operations = data.get("operations", [])

    _sync_registry_molecule_data(research, result)

    research.update_symmetry(
        molecule=molecule.get("id", ""),
        point_group=data.get("point_group", ""),
        operations=operations,
    )

    matrices = {
        str(operation.get("id")): operation.get("matrix")
        for operation in operations
        if (
            isinstance(operation, dict)
            and operation.get("id")
            and operation.get("matrix") is not None
        )
    }

    research.update_matrices(matrices)

    representation = data.get("representation", {})

    if representation:
        research.update_representation(representation)

    group_theory = data.get("group_theory", {})

    if group_theory:
        research.update_reduction(group_theory)

    vibrational_analysis = data.get("vibrational_analysis")

    if vibrational_analysis is not None:
        research.update_vibrational_analysis(vibrational_analysis)

    verification = data.get("verification", {})

    if verification:
        research.update_verification(verification)


async def _run_full_analysis(
    research: ResearchSession,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    molecule = str(arguments.get("molecule", "")).strip()

    basis = arguments.get("basis")

    if basis is not None:
        basis = [str(item) for item in basis]

    include_vibrations = bool(
        arguments.get("include_vibrations", False)
    )

    result = await asyncio.to_thread(
        analyze_molecule,
        molecule=molecule,
        basis=basis,
        include_vibrations=include_vibrations,
    )

    _update_research_from_full_analysis(
        research,
        result,
    )

    if result.get("success"):
        verification = (result.get("data") or {}).get("verification") or {}
        if isinstance(verification, dict):
            research.add_verification_record({
                "ts": time.time(),
                "source": "full_analysis",
                "molecule": (result.get("data") or {}).get("molecule", {}).get("id"),
                "status": verification.get("status"),
                "checks": verification.get("checks", {}),
                "errors": verification.get("errors", []),
            })

    return result


async def _run_generate_transformation_matrices(
    research: ResearchSession,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    molecule = str(arguments.get("molecule", "")).strip()
    result = await asyncio.to_thread(analyze_symmetry, molecule=molecule)
    if result.get("success"):
        _sync_registry_molecule_data(research, result, molecule)
        data = result.get("data", {})
        molecule_data = data.get("molecule", {})
        if isinstance(molecule_data, dict):
            research.update_molecule_data(
                {
                    "id": molecule_data.get("id"),
                    "name": molecule_data.get("name"),
                    "formula": molecule_data.get("formula"),
                    "point_group": molecule_data.get("point_group") or data.get("point_group"),
                    "coordinates": molecule_data.get("coordinates", {}),
                    "bonds": molecule_data.get("bonds", []),
                }
            )
        research.update_symmetry(
            molecule=data.get("molecule", molecule),
            point_group=data.get("point_group", ""),
            operations=data.get("operations", []),
        )
        research.update_matrices(data.get("matrices", {}))
    return result


async def _run_analyze_symmetry(
    research: ResearchSession,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    molecule = str(arguments.get("molecule", "")).strip()

    result = await asyncio.to_thread(
        analyze_symmetry,
        molecule=molecule,
    )

    if result.get("success"):
        _sync_registry_molecule_data(research, result, molecule)
        data = result.get("data", {})

        research.update_symmetry(
            molecule=data.get("molecule", molecule),
            point_group=data.get("point_group", ""),
            operations=data.get("operations", []),
        )

        research.update_matrices(
            data.get("matrices", {})
        )

    return result


async def _run_calculate_representation(
    research: ResearchSession,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    molecule = str(arguments.get("molecule", "")).strip()

    basis = arguments.get("basis") or ["x", "y", "z"]
    basis = [str(item) for item in basis]

    operations = arguments.get("operations") or []

    result = await asyncio.to_thread(
        calculate_representation,
        molecule=molecule,
        basis=basis,
        operations=operations,
    )

    if result.get("success"):
        _sync_registry_molecule_data(research, result, molecule)
        research.update_representation(
            result.get("data", {})
        )

    return result


async def _run_control_molecule_viewer(
    research: ResearchSession,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Validate a viewer action for the browser without touching science state."""
    action = str(arguments.get("action", "")).strip().lower()
    allowed = {
        "rotate-left",
        "rotate-right",
        "zoom-in",
        "zoom-out",
        "show-atom-labels",
        "hide-atom-labels",
        "show-element-names",
        "hide-element-names",
        "reset",
        "show-c3-axis",
        "show-c2-axes",
        "show-sigma-h",
        "clear-highlights",
    }

    if action not in allowed:
        return {
            "success": False,
            "tool": "control_molecule_viewer",
            "error": {
                "code": "INVALID_VIEWER_ACTION",
                "message": f"Unsupported viewer action: {action}",
            },
        }

    return {
        "success": True,
        "tool": "control_molecule_viewer",
        "data": {
            "action": action,
        },
        "error": None,
    }


async def _run_verify_representation(
    research: ResearchSession,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    molecule = str(arguments.get("molecule", "")).strip()

    operations = arguments.get("operations") or []

    representation_matrices = (
        arguments.get("representation_matrices") or {}
    )

    characters = arguments.get("characters") or {}

    result = await asyncio.to_thread(
        verify_representation,
        molecule=molecule,
        operations=operations,
        representation_matrices=representation_matrices,
        characters=characters,
    )

    if result.get("success"):
        _sync_registry_molecule_data(research, result, molecule)
        research.update_verification(
            result.get("data", {})
        )

    return result


async def _run_test_symmetry_operation(research: ResearchSession, arguments: dict[str, Any]) -> dict[str, Any]:
    molecule = str(arguments.get("molecule") or research.molecule or "").strip()
    operation = arguments.get("operation") or {}
    if not molecule:
        return {"success": False, "tool": "operation_test", "error": {"code": "NO_MOLECULE", "message": "No current molecule is available."}}
    result = await asyncio.to_thread(run_molecule_operation, molecule, operation)
    research.append_memory({"ts": time.time(), "kind": "calculation", "tool": "test_symmetry_operation", "molecule": molecule, "operation": _json_safe(operation), "success": bool(result.get("success")), "is_symmetry": (result.get("data") or {}).get("is_symmetry") if result.get("success") else None})
    return result


async def _run_tool(
    research: ResearchSession,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch an AssemblyAI tool.call to an existing VoiceLab science tool."""

    logger.info(
        "AssemblyAI tool call name=%s arguments=%s",
        name,
        arguments,
    )

    if name == "full_analysis":
        return await _run_full_analysis(
            research,
            arguments,
        )

    if name == "generate_transformation_matrices":
        return await _run_generate_transformation_matrices(
            research,
            arguments,
        )

    if name == "analyze_symmetry":
        return await _run_analyze_symmetry(
            research,
            arguments,
        )

    if name == "calculate_representation":
        return await _run_calculate_representation(
            research,
            arguments,
        )

    if name == "control_molecule_viewer":
        return await _run_control_molecule_viewer(
            research,
            arguments,
        )

    if name == "verify_representation":
        return await _run_verify_representation(
            research,
            arguments,
        )

    if name == "test_symmetry_operation":
        return await _run_test_symmetry_operation(
            research,
            arguments,
        )

    raise ValueError(
        f"Unknown VoiceLab tool requested by AssemblyAI: {name}"
    )


def _session_config() -> dict[str, Any]:
    """Build the AssemblyAI Voice Agent session configuration."""

    return {
        "system_prompt": INSTRUCTIONS,
        "greeting": (
            "Hello, this is VoiceLab. "
            "The BF3 demonstration molecule is loaded. Say analyze this molecule to begin."
        ),
        "input": {
            "format": {
                "encoding": "audio/pcm",
            },
            "keyterms": KEYTERMS,
            "turn_detection": {
                "vad_threshold": 0.3,
                "min_silence": 400,
                "max_silence": 1200,
                "interrupt_response": True,
            },
            "transcription_mode": "balanced",
        },
        "output": {
            # AssemblyAI Voice Agent API owns TTS.
            # Use a currently supported Voice Agent voice.
            "voice": "anna",
            "format": {
                "encoding": "audio/pcm",
            },
            "volume": 100,
        },
        "tools": SCIENCE_TOOLS,
    }


async def _send_json(
    ws: Any,
    payload: dict[str, Any],
) -> None:
    """Send one JSON event to AssemblyAI."""
    await ws.send(
        json.dumps(
            payload,
            separators=(",", ":"),
        )
    )


async def _send_session_update(ws: Any) -> None:
    """Initialize the AssemblyAI Voice Agent session."""
    await _send_json(
        ws,
        {
            "type": "session.update",
            "session": _session_config(),
        },
    )


async def _audio_to_assemblyai(
    mic_track: rtc.Track,
    ws: Any,
    ready_event: asyncio.Event,
) -> None:
    """Forward LiveKit microphone audio to AssemblyAI."""

    stream = rtc.AudioStream.from_track(
        track=mic_track,
        sample_rate=AUDIO_SAMPLE_RATE,
        num_channels=AUDIO_CHANNELS,
    )

    try:
        async for event in stream:
            # The Voice Agent API requires session.ready before input.audio.
            if not ready_event.is_set():
                continue

            pcm16_bytes = bytes(event.frame.data)

            if not pcm16_bytes:
                continue

            await _send_json(
                ws,
                {
                    "type": "input.audio",
                    "audio": base64.b64encode(
                        pcm16_bytes
                    ).decode("ascii"),
                },
            )

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "LiveKit microphone -> AssemblyAI audio bridge failed"
        )

    finally:
        await stream.aclose()


async def _publish_browser_event(
    room: rtc.Room,
    event: dict[str, Any],
) -> None:
    """Publish a JSON VoiceLab event to the browser over LiveKit data."""
    try:
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        await room.local_participant.publish_data(payload, reliable=True)
    except Exception:
        logger.exception("Failed to publish VoiceLab browser event: %s", event.get("type"))


def _stage_from_text(text: str) -> str | None:
    """Map an explicit user request to the workspace's progressive stage."""
    value = str(text or "").lower().strip()
    if not value:
        return None
    if any(word in value for word in ("verify", "verification", "validate", "check this")):
        return "verification"
    if any(word in value for word in ("representation", "characters", "character")):
        return "representation"
    if any(word in value for word in ("matrix", "matrices", "transformation")):
        return "matrix"
    if any(word in value for word in ("identity", "point group", "symmetry", "molecule", "compound", "analyze")):
        return "identity"
    return None


def _stage_state(research: ResearchSession, stage: str) -> dict[str, Any]:
    """Return only the scientific section requested by the user."""
    state = research.to_dict()
    if stage == "identity":
        return {
            "session_id": research.session_id,
            "molecule": state.get("molecule"),
            "point_group": state.get("point_group"),
            "molecule_data": state.get("molecule_data") or {},
            "operations": state.get("operations") or [],
        }
    if stage == "matrix":
        return {
            "session_id": research.session_id,
            "matrices": state.get("matrices") or {},
        }
    if stage == "representation":
        return {
            "session_id": research.session_id,
            "representation": state.get("representation") or {},
            "characters": state.get("characters") or {},
        }
    if stage == "verification":
        return {
            "session_id": research.session_id,
            "verification": state.get("verification") or {},
        }
    return {"session_id": research.session_id}


async def _assemblyai_to_livekit(
    ws: Any,
    audio_source: rtc.AudioSource,
    room: rtc.Room,
    research: ResearchSession,
    ready_event: asyncio.Event,
) -> None:
    """Forward AssemblyAI reply audio and process Voice Agent events."""

    # Tool execution must never block the AssemblyAI event receiver.
    # Each task owns its call_id and generation so a later/interrupted
    # conversation turn cannot accidentally consume an older tool result.
    pending_tools: list[dict[str, Any]] = []
    tool_tasks: set[asyncio.Task] = set()
    tool_generation = 0
    reply_done_generations: set[int] = set()

    async def _send_tool_result(tool: dict[str, Any]) -> None:
        await _send_json(
            ws,
            {
                "type": "tool.result",
                "call_id": tool["call_id"],
                "result": json.dumps(
                    tool["result"],
                    ensure_ascii=False,
                ),
                "is_error": tool.get("is_error", False),
            },
        )

        logger.info(
            "Tool result sent call_id=%s generation=%s",
            tool["call_id"],
            tool.get("generation"),
        )

    def _track_tool_task(task: asyncio.Task) -> None:
        tool_tasks.add(task)
        task.add_done_callback(tool_tasks.discard)

    async def _execute_tool_call(
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        stage: str | None,
        generation: int,
    ) -> None:
        try:
            result = await _run_tool(
                research,
                tool_name,
                arguments,
            )

            if generation != tool_generation:
                logger.info(
                    "Discarding stale tool result name=%s call_id=%s generation=%s current_generation=%s",
                    tool_name,
                    call_id,
                    generation,
                    tool_generation,
                )
                return

            tool_record = {
                "call_id": str(call_id),
                "result": _json_safe(result),
                "generation": generation,
            }
            pending_tools.append(tool_record)

            # If reply.done already arrived while this calculation was
            # running, deliver the result now instead of waiting for a
            # completely unrelated future reply.done.
            if generation in reply_done_generations:
                pending_tools.remove(tool_record)
                await _send_tool_result(tool_record)

            logger.info(
                "Tool completed name=%s call_id=%s generation=%s",
                tool_name,
                call_id,
                generation,
            )

            research.append_memory({
                "ts": time.time(),
                "kind": "action",
                "tool": tool_name,
                "arguments": _json_safe(arguments),
                "success": bool(result.get("success")),
            })

            if tool_name == "verify_representation" and isinstance(result.get("data"), dict):
                verification_data = result.get("data") or {}
                research.add_verification_record({
                    "ts": time.time(),
                    "source": "voice",
                    "molecule": verification_data.get("molecule"),
                    "status": verification_data.get("status"),
                    "checks": verification_data.get("checks", {}),
                    "errors": verification_data.get("errors", []),
                })

            await _publish_browser_event(
                room,
                {
                    "type": "tool_status",
                    "tool": tool_name,
                    "stage": stage,
                    "state": "completed",
                },
            )

            if tool_name == "control_molecule_viewer" and result.get("success"):
                viewer_data = result.get("data") or {}
                action = viewer_data.get("action")
                if action:
                    await _publish_browser_event(
                        room,
                        {
                            "type": "molecule_action",
                            "action": action,
                        },
                    )

            if stage:
                await _publish_browser_event(
                    room,
                    {
                        "type": "research_state",
                        "state": _stage_state(research, stage),
                    },
                )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.exception(
                "VoiceLab tool failed name=%s call_id=%s",
                tool_name,
                call_id,
            )

            if generation != tool_generation:
                logger.info(
                    "Discarding stale failed tool result name=%s call_id=%s",
                    tool_name,
                    call_id,
                )
                return

            tool_record = {
                "call_id": str(call_id),
                "result": {
                    "success": False,
                    "error": str(exc),
                },
                "is_error": True,
                "generation": generation,
            }
            pending_tools.append(tool_record)

            if generation in reply_done_generations:
                pending_tools.remove(tool_record)
                await _send_tool_result(tool_record)

    try:
        async for raw in ws:
            event = json.loads(raw)

            event_type = event.get("type")

            if event_type == "session.ready":
                session_id = event.get("session_id")

                logger.info(
                    "AssemblyAI Voice Agent session ready "
                    "session_id=%s room_session=%s",
                    session_id,
                    research.session_id,
                )

                ready_event.set()

                continue

            if event_type == "session.updated":
                logger.debug(
                    "AssemblyAI session configuration updated"
                )
                continue

            if event_type == "input.speech.started":
                # A new speech turn invalidates tool results belonging to an
                # older interrupted turn. The underlying deterministic
                # calculation is allowed to finish safely in its thread, but
                # its result will not be fed into the new conversation turn.
                tool_generation += 1
                pending_tools.clear()

                # Flush any queued TTS immediately on barge-in.
                audio_source.clear_queue()
                await _publish_browser_event(
                    room,
                    {"type": "voice_state", "state": "listening", "message": "Listening..."},
                )

                logger.debug(
                    "User speech started; cleared VoiceLab audio queue"
                )

                continue

            if event_type == "input.speech.stopped":
                logger.debug("User speech stopped")
                continue

            if event_type == "transcript.user.delta":
                delta = event.get("text", "")
                logger.debug("User transcript delta: %s", delta)
                await _publish_browser_event(
                    room,
                    {"type": "transcript", "role": "user", "text": delta, "final": False},
                )
                continue

            if event_type == "transcript.user":
                text = event.get("text", "")

                logger.info("USER: %s", text)
                if text:
                    research.append_memory({"ts": time.time(), "kind": "user", "text": text})
                await _publish_browser_event(
                    room,
                    {"type": "transcript", "role": "user", "text": text, "final": True},
                )

                stage = _stage_from_text(text)
                if stage:
                    await _publish_browser_event(
                        room,
                        {"type": "tool_status", "tool": stage, "stage": stage, "state": "running"},
                    )

                continue

            if event_type == "reply.started":
                await _publish_browser_event(
                    room,
                    {"type": "voice_state", "state": "speaking", "message": "Speaking..."},
                )
                logger.info(
                    "AssemblyAI reply started reply_id=%s",
                    event.get("reply_id"),
                )
                continue

            if event_type == "reply.audio":
                encoded_audio = event.get("data")

                if not encoded_audio:
                    continue

                pcm = base64.b64decode(
                    encoded_audio
                )

                if not pcm:
                    continue

                samples = len(pcm) // 2

                frame = rtc.AudioFrame(
                    data=pcm,
                    sample_rate=AUDIO_SAMPLE_RATE,
                    num_channels=AUDIO_CHANNELS,
                    samples_per_channel=samples,
                )

                await audio_source.capture_frame(frame)

                continue

            if event_type == "transcript.agent.delta":
                delta = event.get("delta", event.get("text", ""))
                logger.debug("Agent transcript delta: %s", delta)
                await _publish_browser_event(
                    room,
                    {"type": "transcript", "role": "assistant", "text": delta, "final": False},
                )
                continue

            if event_type == "transcript.agent":
                text = event.get("text", "")

                logger.info("AGENT: %s", text)
                if text:
                    research.append_memory({"ts": time.time(), "kind": "assistant", "text": text})
                await _publish_browser_event(
                    room,
                    {"type": "transcript", "role": "assistant", "text": text, "final": True},
                )
                continue

            if event_type == "tool.call":
                call_id = event.get("call_id")
                name = event.get("name")
                arguments = event.get("arguments") or {}

                if not call_id or not name:
                    logger.error(
                        "Malformed AssemblyAI tool.call: %s",
                        event,
                    )
                    continue

                tool_name = str(name)
                stage = {
                    "full_analysis": "identity",
                    "analyze_symmetry": "identity",
                    "generate_transformation_matrices": "matrix",
                    "calculate_representation": "representation",
                    "verify_representation": "verification",
                    "control_molecule_viewer": None,
                    "test_symmetry_operation": "verification",
                }.get(tool_name)

                await _publish_browser_event(
                    room,
                    {
                        "type": "tool_status",
                        "tool": tool_name,
                        "stage": stage,
                        "state": "running",
                    },
                )

                task = asyncio.create_task(
                    _execute_tool_call(
                        call_id=str(call_id),
                        tool_name=tool_name,
                        arguments=dict(arguments),
                        stage=stage,
                        generation=tool_generation,
                    ),
                    name=f"voicelab-tool-{call_id}",
                )
                _track_tool_task(task)

                logger.info(
                    "Tool task started name=%s call_id=%s generation=%s",
                    tool_name,
                    call_id,
                    tool_generation,
                )

                continue

            if event_type == "reply.done":
                status = event.get("status")

                await _publish_browser_event(
                    room,
                    {
                        "type": "voice_state",
                        "state": "ready",
                        "message": "Ready",
                    },
                )

                logger.info(
                    "AssemblyAI reply done status=%s",
                    status,
                )

                if status == "interrupted":
                    research.append_memory({"ts": time.time(), "kind": "interrupt", "status": "interrupted"})
                    audio_source.clear_queue()

                    # Invalidate results belonging to the interrupted turn.
                    tool_generation += 1
                    pending_tools.clear()

                    continue

                # Mark this generation as having reached reply.done.
                # Tool results that completed before this point are flushed
                # now. Results that complete later are sent by
                # _execute_tool_call() as soon as they finish.
                reply_done_generations.add(tool_generation)

                if pending_tools:
                    tools_to_send = [
                        tool
                        for tool in pending_tools
                        if tool.get("generation") == tool_generation
                    ]

                    for tool in tools_to_send:
                        if tool in pending_tools:
                            pending_tools.remove(tool)
                        await _send_tool_result(tool)

                continue

            if event_type == "session.error":
                logger.error(
                    "AssemblyAI session error code=%s message=%s event=%s",
                    event.get("code"),
                    event.get("message"),
                    event,
                )
                await _publish_browser_event(
                    room,
                    {
                        "type": "error",
                        "message": event.get("message") or event.get("code") or "AssemblyAI voice error",
                    },
                )
                ready_event.clear()
                continue

            if event_type == "session.ended":
                logger.info(
                    "AssemblyAI session ended duration=%s "
                    "audio_duration=%s",
                    event.get("session_duration_seconds"),
                    event.get("audio_duration_seconds"),
                )
                ready_event.clear()
                continue

            logger.debug(
                "Unhandled AssemblyAI event: %s",
                event_type,
            )

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "AssemblyAI -> LiveKit event bridge failed"
        )

    finally:
        ready_event.clear()


async def _publish_agent_audio(
    room: rtc.Room,
) -> rtc.AudioSource:
    """Create and publish the agent's outgoing LiveKit audio track."""

    audio_source = rtc.AudioSource(
        sample_rate=AUDIO_SAMPLE_RATE,
        num_channels=AUDIO_CHANNELS,
        queue_size_ms=1000,
    )

    local_track = rtc.LocalAudioTrack.create_audio_track(
        AGENT_TRACK_NAME,
        audio_source,
    )

    await room.local_participant.publish_track(
        local_track,
        rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_MICROPHONE,
        ),
    )

    logger.info(
        "Published VoiceLab agent audio track identity=%s track=%s",
        room.local_participant.identity,
        AGENT_TRACK_NAME,
    )

    return audio_source


async def _wait_for_microphone_track(
    room: rtc.Room,
) -> rtc.RemoteAudioTrack:
    """Wait for the first remote microphone audio track."""

    loop = asyncio.get_running_loop()
    future: asyncio.Future[rtc.RemoteAudioTrack] = loop.create_future()

    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if future.done():
            return

        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        if publication.source != rtc.TrackSource.SOURCE_MICROPHONE:
            return

        logger.info(
            "Microphone track subscribed participant=%s source=%s",
            participant.identity,
            publication.source,
        )

        future.set_result(
            track  # type: ignore[arg-type]
        )

    room.on(
        "track_subscribed",
        on_track_subscribed,
    )

    # Check participants that may already have published their microphone
    # before our listener was registered.
    for participant in room.remote_participants.values():
        for publication in participant.track_publications.values():
            if publication.kind != rtc.TrackKind.KIND_AUDIO:
                continue

            if publication.source != rtc.TrackSource.SOURCE_MICROPHONE:
                continue

            if publication.track is not None:
                logger.info(
                    "Found existing microphone track participant=%s",
                    participant.identity,
                )

                if not future.done():
                    future.set_result(
                        publication.track  # type: ignore[arg-type]
                    )

                break

        if future.done():
            break

    try:
        return await future

    finally:
        try:
            room.off(
                "track_subscribed",
                on_track_subscribed,
            )
        except Exception:
            pass


async def _run_bridge(
    ctx: JobContext,
    research: ResearchSession,
) -> None:
    """Run the complete LiveKit <-> AssemblyAI bridge.

    Important ordering:
        1. Publish the agent audio track immediately.
        2. Connect/configure AssemblyAI immediately.
        3. Wait for session.ready so the greeting/TTS can flow.
        4. Only then wait for the browser microphone and stream input.audio.

    The previous implementation waited for the browser microphone before even
    opening the AssemblyAI session. That made the voice path appear silent and
    prevented the agent greeting from ever reaching the browser until the
    microphone track was successfully discovered.
    """

    api_key = os.getenv("ASSEMBLYAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ASSEMBLYAI_API_KEY is not configured."
        )

    room = ctx.room

    # Publish the outgoing agent track first so the browser can subscribe to
    # it even before the AssemblyAI greeting is generated.
    audio_source = await _publish_agent_audio(room)

    logger.info(
        "VoiceLab bridge published agent audio; starting AssemblyAI "
        "room=%s research_session=%s",
        room.name,
        research.session_id,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    async with websockets.connect(
        ASSEMBLYAI_WS_URL,
        additional_headers=headers,
        ping_interval=20,
        ping_timeout=20,
        max_size=None,
    ) as ws:

        # AssemblyAI must receive session.update first, then we wait for
        # session.ready before sending any microphone audio.
        await _send_session_update(ws)

        ready_event = asyncio.Event()

        receiver_task = asyncio.create_task(
            _assemblyai_to_livekit(
                ws=ws,
                audio_source=audio_source,
                room=room,
                research=research,
                ready_event=ready_event,
            )
        )

        mic_task: asyncio.Task | None = None
        mic_bridge_task: asyncio.Task | None = None

        try:
            # Give AssemblyAI a bounded amount of time to acknowledge
            # session.update with session.ready.
            try:
                await asyncio.wait_for(
                    ready_event.wait(),
                    timeout=15.0,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "AssemblyAI Voice Agent did not send session.ready "
                    "within 15 seconds."
                )

            logger.info(
                "AssemblyAI ready; VoiceLab TTS is available "
                "room=%s research_session=%s",
                room.name,
                research.session_id,
            )

            await _publish_browser_event(
                room,
                {
                    "type": "voice_state",
                    "state": "ready",
                    "message": "Voice ready",
                },
            )

            # The browser may not have enabled its microphone yet. Waiting for
            # it here no longer blocks the AssemblyAI session or its greeting.
            await _publish_browser_event(
                room,
                {
                    "type": "voice_state",
                    "state": "ready",
                    "message": "Ready — click V to speak",
                },
            )

            logger.info(
                "Waiting for browser microphone track "
                "room=%s research_session=%s",
                room.name,
                research.session_id,
            )

            mic_task = asyncio.create_task(
                _wait_for_microphone_track(room),
                name=f"voicelab-mic-wait-{research.session_id}",
            )

            mic_track = await mic_task

            logger.info(
                "VoiceLab microphone track received; starting input.audio "
                "bridge room=%s research_session=%s",
                room.name,
                research.session_id,
            )

            await _publish_browser_event(
                room,
                {
                    "type": "voice_state",
                    "state": "listening",
                    "message": "Listening...",
                },
            )

            # Keep microphone forwarding in the current bridge task. The
            # receiver task continues independently so TTS/transcripts/tool
            # events are handled while input audio is streaming.
            await _audio_to_assemblyai(
                mic_track=mic_track,
                ws=ws,
                ready_event=ready_event,
            )

        finally:
            for task in (mic_task, mic_bridge_task, receiver_task):
                if task is None or task.done():
                    continue
                task.cancel()

            for task in (mic_task, mic_bridge_task, receiver_task):
                if task is None:
                    continue
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("VoiceLab bridge task failed during shutdown")

            try:
                audio_source.clear_queue()
            except Exception:
                pass


@server.rtc_session(agent_name="voicelab")
async def entrypoint(ctx: JobContext) -> None:
    """LiveKit dispatch entrypoint."""

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    research = _state_for_room(
        ctx.room.name
    )

    await ctx.connect()

    logger.info(
        "VoiceLab LiveKit transport connected "
        "room=%s research_session=%s",
        ctx.room.name,
        research.session_id,
    )

    try:
        await _run_bridge(
            ctx,
            research,
        )

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "VoiceLab LiveKit / AssemblyAI bridge failed "
            "room=%s research_session=%s",
            ctx.room.name,
            research.session_id,
        )
        raise


if __name__ == "__main__":
    cli.run_app(server)
