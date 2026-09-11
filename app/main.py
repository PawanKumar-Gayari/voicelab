"""
VoiceLab application entry point.

Architecture:

    Browser
        ↓
    FastAPI
        ↓
    VoiceSession
        ↓
    AssemblyAI Voice Agent
        ↓
    VoiceLab tools
        ↓
    Scientific calculation layer

The frontend has exactly three screens:
    home.html
    workspace.html
    result.html
"""

from __future__ import annotations

import asyncio
import base64
import json
import hmac
import logging
import os
import re
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agent.state import _database_config, get_session, session_events
from app.config.settings import settings
from app.report.generator import generate_report
from app.voice.session import (
    close_voice_session,
    create_voice_session,
    get_voice_session,
)
from app.voice.livekit_token import create_voice_token


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

TEMPLATES_DIR = BASE_DIR / "web" / "templates"
STATIC_DIR = BASE_DIR / "web" / "static"


# ----------------------------------------------------------------------
# FastAPI application
# ----------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    description="Voice-first AI research assistant.",
    version="1.0.0",
    debug=settings.debug,
)




# Avoid leaking framework/server details through default exception responses.

# ----------------------------------------------------------------------
# Static files / templates
# ----------------------------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

templates = Jinja2Templates(
    directory=TEMPLATES_DIR,
)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(
        request=request,
        name="404.html",
        status_code=404,
        context={
            "app_name": settings.app_name,
        },
    )


@app.on_event("startup")
async def validate_production_configuration() -> None:
    """Fail fast when a production deployment is missing security/provider configuration."""
    if _database_config()[1] == "postgres":
        from app.agent.postgres_store import ensure_schema
        ensure_schema()
    if settings.environment.lower() != "production":
        return
    required = {
        "ASSEMBLYAI_API_KEY": os.getenv("ASSEMBLYAI_API_KEY", "").strip(),
        "LIVEKIT_URL": os.getenv("LIVEKIT_URL", "").strip(),
        "LIVEKIT_API_KEY": os.getenv("LIVEKIT_API_KEY", "").strip(),
        "LIVEKIT_API_SECRET": os.getenv("LIVEKIT_API_SECRET", "").strip(),
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing required production configuration: " + ", ".join(missing))


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, Any]:
    """
    Simple health endpoint.

    This endpoint does not require AssemblyAI to be configured because
    it is also useful for checking whether the FastAPI application itself
    is running.
    """
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "voice_configured": bool(settings.assemblyai_api_key.strip()),
        "database_backend": _database_config()[1],
    }


# ----------------------------------------------------------------------
# Screen 1 - Home
# ----------------------------------------------------------------------

@app.get(
    "/",
    response_class=HTMLResponse,
)
async def home(
    request: Request,
) -> HTMLResponse:
    """
    Render the VoiceLab home screen.
    """
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "app_name": settings.app_name,
        },
    )


# ----------------------------------------------------------------------
# About
# ----------------------------------------------------------------------

@app.get(
    "/about",
    response_class=HTMLResponse,
)
async def about(
    request: Request,
) -> HTMLResponse:
    """Render the VoiceLab About page."""
    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={"app_name": settings.app_name},
    )


# ----------------------------------------------------------------------
# Screen 2 - Research Workspace
# ----------------------------------------------------------------------

@app.get(
    "/workspace",
    response_class=HTMLResponse,
)
async def workspace(
    request: Request,
    session_id: str | None = None,
) -> HTMLResponse:
    if session_id:
        _owned_research_session(request, session_id)
    """
    Render the research workspace.

    If no session exists yet, the browser can create one through
    POST /api/sessions.
    """
    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context={
            "app_name": settings.app_name,
            "session_id": session_id,
            "livekit_url": os.getenv("LIVEKIT_URL", ""),
        },
    )


# ----------------------------------------------------------------------
# Screen 3 - Result
# ----------------------------------------------------------------------

@app.get(
    "/result",
    response_class=HTMLResponse,
)
async def result_screen(
    request: Request,
    session_id: str | None = None,
) -> HTMLResponse:
    if session_id:
        _owned_research_session(request, session_id)
    """
    Render the final verified-result screen.
    """
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "app_name": settings.app_name,
            "session_id": session_id,
        },
    )


# ----------------------------------------------------------------------
# Research replay page
# ----------------------------------------------------------------------
@app.get(
    "/research/replay/{session_id}",
    response_class=HTMLResponse,
)
async def research_replay_page(
    request: Request,
    session_id: str,
) -> HTMLResponse:
    """
    Render a human-readable replay of a persisted research session.

    Replay data remains owned by the authenticated user and is rendered
    by replay.js from the existing persisted replay API.
    """

    _owned_research_session(request, session_id)

    return templates.TemplateResponse(
        request=request,
        name="replay.html",
        context={
            "app_name": settings.app_name,
            "session_id": session_id,
        },
    )


# ----------------------------------------------------------------------
# Research session API
# ----------------------------------------------------------------------
def _owned_research_session(request: Request, session_id: str):
    """Return a persisted research session without requiring user authentication."""
    research = get_session(session_id)

    if research is None:
        voice_session = get_voice_session(session_id)
        research = voice_session.research_session if voice_session else None

    if research is None:
        raise HTTPException(status_code=404, detail="Research session not found.")

    return research



@app.post("/api/sessions")
async def create_research_session(request: Request) -> dict[str, Any]:
    """
    Create a new VoiceLab research/voice session.
    """
    voice_session = create_voice_session()

    return {
        "success": True,
        "session_id": voice_session.session_id,
        "state": voice_session.get_state(),
    }


@app.get("/api/sessions/{session_id}")
async def get_research_session(
    request: Request,
    session_id: str,
) -> dict[str, Any]:
    """
    Return the current research state.
    """
    owned = _owned_research_session(request, session_id)
    voice_session = get_voice_session(
        session_id
    )

    if voice_session is not None:
        return {
            "success": True,
            "session_id": session_id,
            # SQLite is the authoritative cross-process research state.
            "state": owned.to_dict(),
            "voice": {
                "connected": voice_session.is_connected,
                "ready": voice_session.is_ready,
                "assembly_session_id": (
                    voice_session.assembly_session_id
                ),
            },
        }

    research_session = get_session(
        session_id
    )

    if research_session is None:
        raise HTTPException(
            status_code=404,
            detail="Research session not found.",
        )

    return {
        "success": True,
        "session_id": session_id,
        "state": research_session.to_dict(),
    }



@app.post("/api/sessions/{session_id}/text")
async def submit_text_command(
    request: Request,
    session_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute a typed VoiceLab command through the same deterministic tools used by voice."""
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text command is empty.")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Text command is too long.")

    research = _owned_research_session(request, session_id)
    if research is None:
        voice_session = get_voice_session(session_id)
        research = voice_session.research_session if voice_session else None
    if research is None:
        raise HTTPException(status_code=404, detail="Research session not found.")

    from app.voice.livekit_agent import _run_tool

    normalized = text.lower().strip()
    compact = re.sub(r"[^a-z0-9+#-]", "", normalized)

    viewer_actions = [
        (r"\b(show|display|highlight)\b.*\b(c3|c₃|c3 axis|principal axis)\b", "show-c3-axis"),
        (r"\b(show|display|highlight)\b.*\b(c2|c₂|c2 axes|c2 prime)\b", "show-c2-axes"),
        (r"\b(show|display|highlight)\b.*\b(sigma[- ]?h|σh|molecular plane)\b", "show-sigma-h"),
        (r"\b(clear|hide|remove)\b.*\b(highlights?|axes|planes)\b", "clear-highlights"),
        (r"\b(show|display|enable)\b.*\b(atom labels?|labels?)\b", "show-atom-labels"),
        (r"\b(hide|disable|remove)\b.*\b(atom labels?|labels?)\b", "hide-atom-labels"),
        (r"\b(show|display|enable)\b.*\b(element names?|elements?)\b", "show-element-names"),
        (r"\b(hide|disable|remove)\b.*\b(element names?|elements?)\b", "hide-element-names"),
        (r"\b(rotate|turn)\b.*\bleft\b", "rotate-left"),
        (r"\b(rotate|turn)\b.*\bright\b", "rotate-right"),
        (r"\b(zoom)\b.*\bin\b", "zoom-in"),
        (r"\b(zoom)\b.*\bout\b", "zoom-out"),
        (r"\b(reset|home|default)\b.*\b(view|viewer|molecule|camera)?\b", "reset"),
    ]
    for pattern, action in viewer_actions:
        if re.search(pattern, normalized):
            result = await _run_tool(research, "control_molecule_viewer", {"action": action})
            research.append_memory({"ts": time.time(), "kind": "action", "tool": "control_molecule_viewer", "arguments": {"action": action}, "success": bool(result.get("success")), "source": "typed"})
            return {"success": bool(result.get("success")), "type": "molecule_action", "action": action, "result": result}

    # Intentional negative-symmetry demo: actually construct and test C4.
    if re.search(r"\b(test|check|try)\b.*\bc4\b|\bc4\b.*\b(test|check)\b", normalized, re.I):
        molecule = research.molecule or "BF3"
        from app.tools.operation_test import run_molecule_operation
        result = await asyncio.to_thread(run_molecule_operation, molecule, {
            "id": "C4_test", "symbol": "C4", "type": "rotation",
            "axis": [0.0, 0.0, 1.0], "angle_deg": 90.0,
        })
        data = result.get("data") or {}
        passed = bool(data.get("is_symmetry")) if result.get("success") else False
        message = (f"C4 {'VERIFIED as a symmetry operation' if passed else 'FAILED'} for {molecule}. "
                   + ("The transformed atomic positions do not match the original molecular arrangement." if not passed else "The transformed atoms match the original arrangement."))
        research.append_memory({"ts": time.time(), "kind": "calculation", "tool": "test_symmetry_operation", "molecule": molecule, "operation": "C4(z,90°)", "success": bool(result.get("success")), "is_symmetry": passed})
        return {"success": bool(result.get("success")), "type": "text_response", "message": message, "tool": "test_symmetry_operation", "result": result}

    molecule = None
    # Resolve an explicitly named molecule from the registry first. Never
    # silently substitute the first registered molecule for a user's request.
    from app.science.molecule_registry import get_molecule, list_molecules

    registered = list_molecules()
    normalized_command = re.sub(r"[^a-z0-9]+", "", normalized)

    # Explicit non-registry molecule formula support.
    # Example: "Analyze CH4" must not silently fall back to the
    # session's current molecule (such as BF3).
    deictic_molecule_request = bool(
        re.search(
            r"\b(?:this|current|the)\s+(?:molecule|compound)\b",
            normalized,
            re.I,
        )
    )

    # Conservative chemical-formula matcher:
    # CH4, CO2, NH3, H2O, BF3, C6H6, etc.
    formula_matches = re.findall(
        r"\b(?:[A-Z][a-z]?\d*){1,6}\b",
        text,
    )

    explicit_matches = []
    for item in registered:
        aliases = (item.get("id", ""), item.get("name", ""), item.get("formula", ""))
        for alias in aliases:
            alias_norm = re.sub(r"[^a-z0-9]+", "", str(alias).lower())
            if alias_norm and re.search(r"(?<![a-z0-9])" + re.escape(str(alias).lower()) + r"(?![a-z0-9])", normalized):
                explicit_matches.append(item.get("id"))
                break
            if alias_norm and alias_norm in normalized_command:
                explicit_matches.append(item.get("id"))
                break

    explicit_matches = list(dict.fromkeys(x for x in explicit_matches if x))
    if len(explicit_matches) == 1:
        molecule = get_molecule(explicit_matches[0]).molecule_id
    elif len(explicit_matches) > 1:
        return {
            "success": False,
            "type": "text_response",
            "message": "I found more than one molecule reference. Please specify the exact molecule or formula.",
        }
    elif formula_matches and not deictic_molecule_request:
        unique_formulas = list(dict.fromkeys(formula_matches))

        if len(unique_formulas) == 1:
            # Allow an unregistered explicit formula to reach full_analysis(),
            # where the external PubChem provider can resolve it.
            molecule = unique_formulas[0]

        elif len(unique_formulas) > 1:
            return {
                "success": False,
                "type": "text_response",
                "message": "I found more than one molecule formula. Please specify the exact molecule.",
            }

    elif research.molecule:
        molecule = get_molecule(str(research.molecule)).molecule_id

    if molecule is None:
        return {
            "success": False,
            "type": "text_response",
            "message": "Please include a registered molecule or analyze one first.",
        }

    # High-level reduction requests must use the complete deterministic
    # dependency pipeline. Do not call calculate_representation directly
    # because representation calculation requires symmetry operations.
    reduction_terms = (
        "representation reduction",
        "reduce representation",
        "reduction of representation",
        "reduce the representation",
        "irreducible representation",
        "irreducible representations",
        "irreps",
        "gamma reduction",
        "gamma reduc",
    )

    is_reduction_request = any(term in normalized for term in reduction_terms)

    if is_reduction_request:
        tool_name, args = "full_analysis", {
            "molecule": molecule,
            "basis": ["x", "y", "z"],
        }
    elif any(term in normalized for term in (
        "full analysis",
        "complete analysis",
        "analyze",
        "analyse",
        "analyze molecule",
        "start analysis",
    )):
        tool_name, args = "full_analysis", {"molecule": molecule}
    elif any(term in normalized for term in (
        "transformation matrix",
        "transformation matrices",
        "matrices",
        "matrix",
    )):
        tool_name, args = "generate_transformation_matrices", {"molecule": molecule}
    elif any(term in normalized for term in (
        "representation",
        "characters",
        "character",
    )):
        tool_name, args = "calculate_representation", {
            "molecule": molecule,
            "basis": ["x", "y", "z"],
        }
    elif any(term in normalized for term in (
        "verify",
        "verification",
        "validate",
        "check",
    )):
        state = research.to_dict()
        args = {
            "molecule": molecule,
            "operations": state.get("operations", []),
            "representation_matrices": state.get("representation", {}).get("representation_matrices", {}) or state.get("matrices", {}),
            "characters": state.get("characters", {}),
        }
        tool_name = "verify_representation"
    else:
        tool_name, args = "analyze_symmetry", {"molecule": molecule}

    result = await _run_tool(research, tool_name, args)
    data = result.get("data") or {}
    if not result.get("success"):
        error = result.get("error")
        error_code = error.get("code", "") if isinstance(error, dict) else ""

        if is_reduction_request:
            message = (
                f"I couldn't complete the representation reduction for {molecule}. "
                "The scientific analysis pipeline could not produce a verified result."
            )
        elif error_code == "INVALID_OPERATIONS":
            message = (
                "I need the molecule's symmetry operations before I can complete "
                "that calculation. Please run the symmetry analysis first."
            )
        else:
            message = "I couldn't complete that scientific calculation. Please try again."

        return {
            "success": False,
            "type": "text_response",
            "message": message,
        }

    point_group = data.get("point_group") or research.point_group
    if tool_name == "full_analysis":
        if is_reduction_request:
            reduction = (
                data.get("group_theory", {}).get("reduction", {})
                if isinstance(data, dict)
                else {}
            )
            reduction_summary = (
                reduction.get("summary")
                if isinstance(reduction, dict)
                else None
            )

            message = (
                f"Representation reduction completed for {molecule}. "
                f"Point group: {point_group or 'shown in the analysis panel'}."
            )

            if reduction_summary:
                message += f" {reduction_summary}"
        else:
            message = (
                f"Completed the full symmetry analysis for {molecule}. "
                f"Point group: {point_group or 'available in the analysis panel'}."
            )
    elif tool_name == "analyze_symmetry":
        message = f"Symmetry analysis completed for {molecule}. Point group: {point_group or 'shown in the analysis panel'}."
    elif tool_name == "generate_transformation_matrices":
        message = f"Transformation matrices for {molecule} are now available in the workspace."
    elif tool_name == "calculate_representation":
        message = f"The Cartesian representation and characters for {molecule} are now available."
    else:
        verification = data.get("verification") if isinstance(data, dict) else None
        message = f"Verification completed for {molecule}."
        if isinstance(verification, dict) and verification.get("passed") is not None:
            message += " PASS." if verification.get("passed") else " The verification did not pass."

    research.append_memory({"ts": time.time(), "kind": "typed", "text": text, "tool": tool_name, "success": True})
    return {"success": True, "type": "text_response", "message": message, "tool": tool_name, "result": result}

@app.post("/api/sessions/{session_id}/vision")
async def analyze_screen_vision(
    request: Request,
    session_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Analyze a user-approved workspace screenshot with Gemini vision.

    The vision agent observes the UI; it does not mutate scientific state or
    execute commands. This separation keeps screen understanding safe and
    deterministic while still allowing the agent to explain what is visible.
    """
    research = _owned_research_session(request, session_id)
    if research is None:
        voice_session = get_voice_session(session_id)
        research = voice_session.research_session if voice_session else None
    if research is None:
        raise HTTPException(status_code=404, detail="Research session not found.")

    image = str(payload.get("image_base64", "")).strip()
    if not image:
        raise HTTPException(status_code=400, detail="image_base64 is required.")
    if len(image) > 8_000_000:
        raise HTTPException(status_code=413, detail="Screenshot is too large.")

    # Accept either a raw base64 payload or a data URL.
    mime = "image/png"
    if image.startswith("data:"):
        header, _, image = image.partition(",")
        match = re.match(r"data:([^;]+);base64", header, re.I)
        if match:
            mime = match.group(1)

    try:
        raw = base64.b64decode(image, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid screenshot encoding.") from exc
    if not raw or len(raw) > 6_000_000:
        raise HTTPException(status_code=413, detail="Screenshot is too large.")

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="GOOGLE_API_KEY is not configured.")

    current_state = research.to_dict()
    prompt = f"""You are VoiceLab Screen Vision, a UI-understanding assistant.
Prefer this structured application state when available, and use the screenshot to confirm what is visibly present.
Structured state: {json.dumps({"molecule": current_state.get("molecule"), "molecule_data": current_state.get("molecule_data", {{}}), "point_group": current_state.get("point_group"), "operations": current_state.get("operations", [])}, default=str)[:12000]}
Analyze this screenshot of the VoiceLab scientific workspace. Return concise JSON with:
summary: one sentence describing what is visible;
ui_elements: array of important visible controls/cards/statuses;
scientific_context: molecule, point group, or analysis state only when visibly supported;
issues: array of concrete visual/UI problems;
suggested_actions: array of useful user actions phrased as commands.
Do not invent text or scientific results that are not visible. Do not execute anything.
"""

    request_body = json.dumps({
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode("ascii")}},
        ]}]
    }).encode("utf-8")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + urllib.parse.quote(api_key)
    request = urllib.request.Request(url, data=request_body, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"Vision model error: {detail}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Vision request failed: {exc}") from exc

    text = ""
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="Vision model returned no usable analysis.")

    parsed: Any = None
    try:
        cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
        parsed = json.loads(cleaned)
    except Exception:
        parsed = {"summary": text.strip(), "ui_elements": [], "scientific_context": {}, "issues": [], "suggested_actions": []}

    research.append_memory({
        "ts": time.time(),
        "kind": "vision",
        "summary": str(parsed.get("summary", ""))[:500] if isinstance(parsed, dict) else str(parsed)[:500],
    })
    return {"success": True, "vision": parsed}


@app.post("/api/sessions/{session_id}/viewer-state")
async def report_viewer_state(request: Request, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Record the browser's actual viewer state for action verification/recovery."""
    research = _owned_research_session(request, session_id)
    state = {
        "action": str(payload.get("action", "")),
        "atom_labels": bool(payload.get("atom_labels", False)),
        "element_names": bool(payload.get("element_names", False)),
        "highlight": str(payload.get("highlight", "none")),
    }
    research.append_memory({"ts": time.time(), "kind": "viewer_state", **state})
    return {"success": True, "state": state}


@app.get("/api/sessions/{session_id}/replay")
async def replay_session(request: Request, session_id: str) -> dict[str, Any]:
    """Return the durable chronological agent memory for replay."""
    research = _owned_research_session(request, session_id)
    if research is None:
        raise HTTPException(status_code=404, detail="Research session not found.")
    state = research.to_dict()

    return {
        "success": True,
        "session_id": session_id,
        "version": state.get("version", 0),
        "state": state,
        "events": session_events(session_id),
        "memory": state.get("memory", []),
        "verification_history": state.get("verification_history", []),
    }


@app.post("/api/sessions/{session_id}/reset")
async def reset_research_session(
    request: Request,
    session_id: str,
) -> dict[str, Any]:
    """
    Reset the complete research state for a session.

    This is used when the user starts a fresh research workspace. The
    existing session ID is retained so LiveKit/voice routing remains stable,
    but all previous scientific results are removed from shared SQLite state.
    """
    _owned_research_session(request, session_id)

    voice_session = get_voice_session(session_id)

    if voice_session is not None:
        voice_session.research_session.reset()
        return {
            "success": True,
            "session_id": session_id,
            "state": voice_session.get_state(),
        }

    research_session = get_session(session_id)

    if research_session is None:
        raise HTTPException(
            status_code=404,
            detail="Research session not found.",
        )

    research_session.reset()

    return {
        "success": True,
        "session_id": session_id,
        "state": research_session.to_dict(),
    }


# ----------------------------------------------------------------------
# LiveKit browser token API
# ----------------------------------------------------------------------

@app.get("/api/livekit/token")
async def get_livekit_token(
    request: Request,
    room: str,
    identity: str,
) -> dict[str, Any]:
    """
    Issue a short-lived LiveKit token for the browser.

    The browser receives only the signed token. LiveKit API credentials
    remain server-side in the environment.
    """
    livekit_url = os.getenv("LIVEKIT_URL", "").strip()

    if not livekit_url:
        raise HTTPException(
            status_code=503,
            detail="LIVEKIT_URL is not configured.",
        )

    if not os.getenv("LIVEKIT_API_KEY", "").strip():
        raise HTTPException(
            status_code=503,
            detail="LIVEKIT_API_KEY is not configured.",
        )

    if not os.getenv("LIVEKIT_API_SECRET", "").strip():
        raise HTTPException(
            status_code=503,
            detail="LIVEKIT_API_SECRET is not configured.",
        )

    room = room.strip()
    identity = identity.strip()

    if not room.startswith("voicelab-"):
        raise HTTPException(status_code=400, detail="Invalid VoiceLab room.")
    session_id = room.removeprefix("voicelab-")
    _owned_research_session(request, session_id)
    if identity != "researcher-" + session_id:
        raise HTTPException(status_code=403, detail="Invalid session identity.")

    if not room:
        raise HTTPException(
            status_code=400,
            detail="room is required.",
        )

    if not identity:
        raise HTTPException(
            status_code=400,
            detail="identity is required.",
        )

    try:
        token = create_voice_token(
            room_name=room,
            identity=identity,
        )
    except Exception as exc:
        logger.exception("Failed to create LiveKit token.")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create LiveKit token: {exc}",
        ) from exc

    return {
        "success": True,
        "token": token,
        "url": livekit_url,
        "room": room,
        "identity": identity,
    }


# ----------------------------------------------------------------------
# Report API
# ----------------------------------------------------------------------

@app.get(
    "/api/sessions/{session_id}/report",
    response_class=HTMLResponse,
)
async def get_report(
    request: Request,
    session_id: str,
) -> HTMLResponse:
    """
    Generate and return the current research report.

    The report is generated from the deterministic research state.
    """
    _owned_research_session(request, session_id)

    voice_session = get_voice_session(
        session_id
    )

    if voice_session is not None:
        research_session = voice_session.research_session
    else:
        research_session = get_session(
            session_id
        )

    if research_session is None:
        raise HTTPException(
            status_code=404,
            detail="Research session not found.",
        )

    report = generate_report(
        research_session
    )

    research_session.update_report(
        report
    )

    return HTMLResponse(
        content=report,
        status_code=200,
    )


# ----------------------------------------------------------------------
# Voice WebSocket
# ----------------------------------------------------------------------

@app.websocket("/ws/voice/{session_id}")
async def voice_websocket(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    Browser <-> VoiceLab voice bridge.

    Browser sends:

        {
            "type": "audio",
            "data": "<base64 PCM audio>"
        }

    Browser may also send:

        {
            "type": "ping"
        }

    Server sends normalized VoiceLab events:

        {
            "type": "transcript",
            ...
        }

        {
            "type": "voice_state",
            ...
        }

        {
            "type": "tool_status",
            ...
        }

        {
            "type": "connection",
            ...
        }
    """
    await websocket.accept()

    voice_session = get_voice_session(
        session_id
    )

    if voice_session is None:
        await websocket.send_json(
            {
                "type": "error",
                "code": "SESSION_NOT_FOUND",
                "message": (
                    "VoiceLab research session was not found."
                ),
            }
        )

        await websocket.close(
            code=1008,
            reason="Session not found.",
        )

        return

    logger.info(
        "Voice WebSocket connected: %s",
        session_id,
    )

    # --------------------------------------------------------------
    # Start AssemblyAI voice session
    # --------------------------------------------------------------

    try:
        if not voice_session.is_connected:
            await voice_session.start()

    except Exception as exc:
        logger.exception(
            "Failed to start voice session %s",
            session_id,
        )

        await websocket.send_json(
            {
                "type": "error",
                "code": "VOICE_START_FAILED",
                "message": str(exc),
            }
        )

        await websocket.close(
            code=1011,
            reason="Voice agent startup failed.",
        )

        return

    # --------------------------------------------------------------
    # Send current state immediately
    # --------------------------------------------------------------

    await websocket.send_json(
        {
            "type": "state",
            "session_id": session_id,
            "state": voice_session.get_state(),
        }
    )

    # --------------------------------------------------------------
    # Concurrent browser input + AssemblyAI output
    # --------------------------------------------------------------

    async def forward_events() -> None:
        """
        Forward VoiceLab events from the voice session to the browser.
        """
        async for event in voice_session.events():
            try:
                await websocket.send_json(
                    event
                )
            except (
                WebSocketDisconnect,
                RuntimeError,
            ):
                return

    event_task = None

    try:
        import asyncio

        event_task = asyncio.create_task(
            forward_events()
        )

        while True:
            message = await websocket.receive()

            # ------------------------------------------------------
            # Browser disconnect
            # ------------------------------------------------------

            if message.get("type") == "websocket.disconnect":
                break

            # ------------------------------------------------------
            # Binary audio
            # ------------------------------------------------------

            binary_data = message.get(
                "bytes"
            )

            if binary_data is not None:
                await voice_session.send_audio(
                    binary_data
                )

                continue

            # ------------------------------------------------------
            # Text/JSON message
            # ------------------------------------------------------

            text_data = message.get(
                "text"
            )

            if text_data is None:
                continue

            try:
                payload = json.loads(
                    text_data
                )

            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "INVALID_JSON",
                        "message": (
                            "Expected a valid JSON message."
                        ),
                    }
                )
                continue

            message_type = payload.get(
                "type"
            )

            # ------------------------------------------------------
            # Base64 audio
            # ------------------------------------------------------

            if message_type == "audio":
                import base64

                encoded_audio = payload.get(
                    "data"
                )

                if not isinstance(
                    encoded_audio,
                    str,
                ):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "INVALID_AUDIO",
                            "message": (
                                "Audio data must be a "
                                "base64 string."
                            ),
                        }
                    )
                    continue

                try:
                    audio = base64.b64decode(
                        encoded_audio,
                        validate=True,
                    )

                except Exception:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "INVALID_AUDIO",
                            "message": (
                                "Audio data is not valid base64."
                            ),
                        }
                    )
                    continue

                await voice_session.send_audio(
                    audio
                )

                continue

            # ------------------------------------------------------
            # Ping
            # ------------------------------------------------------

            if message_type == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                    }
                )

                continue

            # ------------------------------------------------------
            # State request
            # ------------------------------------------------------

            if message_type == "get_state":
                await websocket.send_json(
                    {
                        "type": "state",
                        "session_id": session_id,
                        "state": voice_session.get_state(),
                    }
                )

                continue

            # ------------------------------------------------------
            # Unknown browser message
            # ------------------------------------------------------

            await websocket.send_json(
                {
                    "type": "error",
                    "code": "UNKNOWN_MESSAGE_TYPE",
                    "message": (
                        f"Unsupported message type: "
                        f"{message_type!r}"
                    ),
                }
            )

    except WebSocketDisconnect:
        logger.info(
            "Voice WebSocket disconnected: %s",
            session_id,
        )

    except Exception as exc:
        logger.exception(
            "Voice WebSocket error for %s",
            session_id,
        )

        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "VOICE_WEBSOCKET_ERROR",
                    "message": str(exc),
                }
            )
        except Exception:
            pass

    finally:
        if event_task is not None:
            event_task.cancel()

            try:
                await event_task
            except asyncio.CancelledError:
                pass

        # ----------------------------------------------------------
        # Important:
        #
        # Do NOT end the AssemblyAI session here.
        #
        # A browser refresh/network interruption should allow the
        # AssemblyAI layer to resume the existing session.
        # ----------------------------------------------------------

        logger.info(
            "Voice WebSocket cleanup completed: %s",
            session_id,
        )


# ----------------------------------------------------------------------
# Application startup / shutdown
# ----------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    """Application startup hook with production configuration guard."""
    logger.info(
        "%s starting on %s:%s",
        settings.app_name,
        settings.app_host,
        settings.app_port,
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """
    Application shutdown hook.

    Active voice sessions are intentionally not individually manipulated
    here because the process is terminating and the in-memory registry
    disappears with the process.
    """
    logger.info(
        "%s shutting down.",
        settings.app_name,
    )


# ----------------------------------------------------------------------
# Local development entry point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
    )