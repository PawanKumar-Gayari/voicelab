"""
AssemblyAI Voice Agent integration for VoiceLab.

Responsibilities:
    - Connect to AssemblyAI Voice Agent API.
    - Configure the VoiceLab agent.
    - Stream audio.
    - Receive and normalize events.
    - Dispatch VoiceLab tools.
    - Handle tool results.
    - Reconnect automatically after transient disconnects.
    - Use exponential backoff for reconnect attempts.
    - Resume an existing AssemblyAI session when possible.
    - Fall back to a fresh session when the previous session expires.

Scientific calculations remain in app/science/.
Tool orchestration remains in app/tools/.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
from typing import Any, AsyncIterator, Callable

import websockets
from websockets.asyncio.client import ClientConnection

from app.agent.system_prompt import get_system_prompt
from app.config.settings import settings
from app.tools.full_analysis import analyze_molecule
from app.tools.representation import calculate_representation
from app.tools.symmetry import analyze_symmetry
from app.tools.verification import verify_representation


logger = logging.getLogger(__name__)


ASSEMBLYAI_VOICE_AGENT_URL = (
    "wss://agents.assemblyai.com/v1/ws"
)

DEFAULT_VOICE = "anna"

SESSION_RESUME_WINDOW_SECONDS = 30.0

DEFAULT_MAX_RECONNECT_ATTEMPTS = 5
DEFAULT_INITIAL_BACKOFF_SECONDS = 0.5
DEFAULT_MAX_BACKOFF_SECONDS = 8.0
DEFAULT_BACKOFF_JITTER_SECONDS = 0.25

SESSION_RESET_ERROR_CODES = {
    "session_not_found",
    "session_forbidden",
    "session_expired",
}


ToolHandler = Callable[
    [dict[str, Any]],
    dict[str, Any],
]


class AssemblyAIVoiceAgent:
    """
    VoiceLab connection to the AssemblyAI Voice Agent API.

    The AssemblyAI session_id is retained across transient disconnects
    so that the next connection can attempt session.resume.
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        voice: str = DEFAULT_VOICE,
        max_reconnect_attempts: int = DEFAULT_MAX_RECONNECT_ATTEMPTS,
        initial_backoff_seconds: float = (
            DEFAULT_INITIAL_BACKOFF_SECONDS
        ),
        max_backoff_seconds: float = (
            DEFAULT_MAX_BACKOFF_SECONDS
        ),
    ) -> None:
        self.system_prompt = (
            system_prompt
            if system_prompt is not None
            else get_system_prompt()
        )

        self.voice = voice

        self.max_reconnect_attempts = max(
            0,
            int(max_reconnect_attempts),
        )

        self.initial_backoff_seconds = max(
            0.0,
            float(initial_backoff_seconds),
        )

        self.max_backoff_seconds = max(
            self.initial_backoff_seconds,
            float(max_backoff_seconds),
        )

        self.websocket: ClientConnection | None = None

        self.assembly_session_id: str | None = None

        self.is_ready = False
        self.is_connected = False

        self._intentional_close = False

        self._reconnect_lock = asyncio.Lock()

        self._disconnect_monotonic: float | None = None

        self._reconnect_attempts = 0

        self.pending_tool_results: list[
            dict[str, Any]
        ] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def reconnect_attempts(self) -> int:
        """Return the current reconnect-attempt count."""
        return self._reconnect_attempts

    @property
    def can_resume_session(self) -> bool:
        """Return whether the saved AssemblyAI session can be resumed."""

        if self.assembly_session_id is None:
            return False

        if self._disconnect_monotonic is None:
            return True

        elapsed = (
            asyncio.get_running_loop().time()
            - self._disconnect_monotonic
        )

        return elapsed < SESSION_RESUME_WINDOW_SECONDS

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------

    @staticmethod
    def get_tool_definitions() -> list[dict[str, Any]]:
        """Return the VoiceLab tools."""

        return [
            {
                "type": "function",
                "name": "analyze_symmetry",
                "description": (
                    "Analyze the molecular symmetry of a registered molecule. "
                    "Use this to identify the point group and obtain "
                    "the complete symmetry operations from the Molecule Registry. "
                    "Only use molecules registered in VoiceLab."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "molecule": {
                            "type": "string",
                            "description": (
                                "Registered molecule to analyze, for example BF3 or H2O."
                            ),
                        }
                    },
                    "required": ["molecule"],
                },
            },
            {
                "type": "function",
                "name": "calculate_representation",
                "description": (
                    "Calculate representation matrices and characters "
                    "for the supplied molecular symmetry operations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "molecule": {
                            "type": "string",
                            "description": "Molecule being analyzed.",
                        },
                        "basis": {
                            "type": "array",
                            "description": (
                                "Cartesian basis functions. "
                                "The current MVP supports x, y, and z."
                            ),
                            "items": {
                                "type": "string",
                            },
                        },
                        "operations": {
                            "type": "array",
                            "description": (
                                "Symmetry operations returned by "
                                "the symmetry analysis tool."
                            ),
                            "items": {
                                "type": "object",
                            },
                        },
                    },
                    "required": [
                        "molecule",
                        "basis",
                        "operations",
                    ],
                },
            },
            {
                "type": "function",
                "name": "full_analysis",
                "description": (
                    "Run the complete symmetry analysis for a registered "
                    "molecule in one step: symmetry operations, "
                    "representation matrices, characters, reduction into "
                    "irreducible representations (using the molecule's "
                    "point group character table), and independent "
                    "verification. Works automatically for any molecule "
                    "and point group registered in VoiceLab, including "
                    "newly added ones. Prefer this over calling "
                    "analyze_symmetry, calculate_representation, and "
                    "verify_representation separately, unless the user "
                    "asks to see one step at a time."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "molecule": {
                            "type": "string",
                            "description": (
                                "Registered molecule to analyze, for "
                                "example BF3 or H2O."
                            ),
                        },
                        "basis": {
                            "type": "array",
                            "description": (
                                "Cartesian basis functions. "
                                "The current MVP supports x, y, and z. "
                                "Defaults to [x, y, z]."
                            ),
                            "items": {
                                "type": "string",
                            },
                        },
                    },
                    "required": ["molecule"],
                },
            },
            {
                "type": "function",
                "name": "verify_representation",
                "description": (
                    "Independently verify the representation matrices "
                    "and characters. Use this when the user asks to "
                    "verify, check, validate, or confirm the result."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "molecule": {
                            "type": "string",
                            "description": "Molecule being analyzed.",
                        },
                        "operations": {
                            "type": "array",
                            "description": (
                                "Symmetry operations used in the "
                                "representation calculation."
                            ),
                            "items": {
                                "type": "object",
                            },
                        },
                        "representation_matrices": {
                            "type": "object",
                            "description": (
                                "Calculated D(g) representation "
                                "matrices keyed by operation ID."
                            ),
                        },
                        "characters": {
                            "type": "object",
                            "description": (
                                "Calculated characters χ(g) keyed "
                                "by operation ID."
                            ),
                        },
                    },
                    "required": [
                        "molecule",
                        "operations",
                        "representation_matrices",
                        "characters",
                    ],
                },
            },
        ]

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(
        self,
        resume_session_id: str | None = None,
    ) -> None:
        """
        Open an AssemblyAI WebSocket connection.

        A valid resumable session uses session.resume.
        Otherwise a fresh session.update is sent.
        """

        if not settings.assemblyai_api_key.strip():
            raise ValueError(
                "ASSEMBLYAI_API_KEY is not configured."
            )

        if self.websocket is not None:
            await self._close_socket_only()

        self._intentional_close = False
        self.is_connected = False
        self.is_ready = False

        headers = {
            "Authorization": (
                f"Bearer {settings.assemblyai_api_key}"
            )
        }

        try:
            self.websocket = await websockets.connect(
                ASSEMBLYAI_VOICE_AGENT_URL,
                additional_headers=headers,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )

            self.is_connected = True

            if resume_session_id:
                self.assembly_session_id = resume_session_id

            if self.can_resume_session:
                await self._send(
                    {
                        "type": "session.resume",
                        "session_id": self.assembly_session_id,
                    }
                )

                logger.info(
                    "Attempting AssemblyAI session resume: %s",
                    self.assembly_session_id,
                )

            else:
                self.assembly_session_id = None
                await self._send_session_update()

                logger.info(
                    "Starting a fresh AssemblyAI session."
                )

        except Exception:
            self.is_connected = False
            self.is_ready = False
            await self._close_socket_only()
            raise

    async def _send_session_update(self) -> None:
        """Send initial configuration for a fresh session."""

        await self._send(
            {
                "type": "session.update",
                "session": {
                    "system_prompt": self.system_prompt,
                    "greeting": (
                        "Welcome to VoiceLab. "
                        "What would you like to analyze?"
                    ),
                    "tools": self.get_tool_definitions(),
                    "output": {
                        "voice": self.voice,
                    },
                },
            }
        )

    # ------------------------------------------------------------------
    # Reconnect logic
    # ------------------------------------------------------------------

    async def reconnect(
        self,
        *,
        reset_session: bool = False,
    ) -> bool:
        """Reconnect with exponential backoff."""

        async with self._reconnect_lock:
            if self.is_connected:
                return True

            if reset_session:
                self.assembly_session_id = None
                self._disconnect_monotonic = None

            if (
                self.assembly_session_id is not None
                and not self.can_resume_session
            ):
                logger.warning(
                    "AssemblyAI resume window expired; "
                    "starting a fresh session."
                )

                self.assembly_session_id = None
                self._disconnect_monotonic = None

            for attempt in range(
                1,
                self.max_reconnect_attempts + 1,
            ):
                self._reconnect_attempts = attempt

                delay = self._calculate_backoff(attempt)

                if attempt > 1:
                    await asyncio.sleep(delay)

                try:
                    await self.connect(
                        resume_session_id=(
                            self.assembly_session_id
                        )
                    )

                    self._reconnect_attempts = 0
                    self._disconnect_monotonic = None

                    logger.info(
                        "AssemblyAI reconnect succeeded "
                        "on attempt %d.",
                        attempt,
                    )

                    return True

                except Exception as exc:
                    logger.warning(
                        "AssemblyAI reconnect attempt %d/%d "
                        "failed: %s",
                        attempt,
                        self.max_reconnect_attempts,
                        exc,
                    )

                    self.is_connected = False
                    self.is_ready = False

            self._reconnect_attempts = 0

            logger.error(
                "AssemblyAI reconnect failed after %d attempts.",
                self.max_reconnect_attempts,
            )

            return False

    def _calculate_backoff(
        self,
        attempt: int,
    ) -> float:
        """Calculate exponential backoff with jitter."""

        exponential = (
            self.initial_backoff_seconds
            * (2 ** max(0, attempt - 1))
        )

        base_delay = min(
            exponential,
            self.max_backoff_seconds,
        )

        jitter = random.uniform(
            0.0,
            DEFAULT_BACKOFF_JITTER_SECONDS,
        )

        return base_delay + jitter

    def _mark_disconnected(self) -> None:
        """Record a transient disconnect."""

        self.is_connected = False
        self.is_ready = False

        if self._disconnect_monotonic is None:
            self._disconnect_monotonic = (
                asyncio.get_running_loop().time()
            )

    # ------------------------------------------------------------------
    # Audio / messages
    # ------------------------------------------------------------------

    async def send_audio(
        self,
        pcm_audio: bytes,
    ) -> None:
        """Send PCM16 mono 24 kHz audio."""

        if not self.is_connected:
            connected = await self.reconnect()

            if not connected:
                raise ConnectionError(
                    "Unable to reconnect to AssemblyAI."
                )

        if not self.is_ready:
            raise RuntimeError(
                "AssemblyAI session is not ready yet."
            )

        if not pcm_audio:
            return

        encoded_audio = base64.b64encode(
            pcm_audio
        ).decode("ascii")

        message = {
            "type": "input.audio",
            "audio": encoded_audio,
        }

        try:
            await self._send(message)

        except (
            websockets.ConnectionClosed,
            ConnectionError,
            OSError,
        ):
            self._mark_disconnected()

            connected = await self.reconnect()

            if not connected:
                raise ConnectionError(
                    "AssemblyAI connection was lost and "
                    "could not be restored."
                )

            await self._send(message)

    async def send_session_update(
        self,
        updates: dict[str, Any],
    ) -> None:
        """Send a mutable session configuration update."""

        if not self.is_connected:
            connected = await self.reconnect()

            if not connected:
                raise ConnectionError(
                    "Unable to reconnect to AssemblyAI."
                )

        await self._send(
            {
                "type": "session.update",
                "session": updates,
            }
        )

    async def end_session(self) -> None:
        """Intentionally end the AssemblyAI session."""

        self._intentional_close = True

        if self.websocket is None:
            return

        try:
            await self._send(
                {
                    "type": "session.end",
                }
            )

        except (
            websockets.ConnectionClosed,
            ConnectionError,
            OSError,
        ):
            pass

        finally:
            self.is_ready = False
            self.is_connected = False
            self.assembly_session_id = None
            self._disconnect_monotonic = None
            self.pending_tool_results.clear()

            await self._close_socket_only()

    async def close(self) -> None:
        """Intentionally close the current connection."""

        self._intentional_close = True

        self.is_ready = False
        self.is_connected = False

        self.assembly_session_id = None
        self._disconnect_monotonic = None
        self.pending_tool_results.clear()

        await self._close_socket_only()

    async def _close_socket_only(self) -> None:
        """Close only the WebSocket."""

        websocket = self.websocket
        self.websocket = None

        if websocket is None:
            return

        try:
            await websocket.close()
        except Exception:
            pass

    async def _send(
        self,
        message: dict[str, Any],
    ) -> None:
        """Send a JSON message to AssemblyAI."""

        if self.websocket is None:
            raise ConnectionError(
                "AssemblyAI WebSocket is not connected."
            )

        await self.websocket.send(
            json.dumps(message)
        )

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def dispatch_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a VoiceLab tool."""

        if not isinstance(arguments, dict):
            return {
                "success": False,
                "tool": name,
                "data": None,
                "error": {
                    "code": "INVALID_ARGUMENTS",
                    "message": (
                        "Tool arguments must be a JSON object."
                    ),
                },
            }

        try:
            allowed_tools = {
                "analyze_symmetry",
                "calculate_representation",
                "verify_representation",
                "full_analysis",
            }

            if name not in allowed_tools:
                return {
                    "success": False,
                    "tool": name,
                    "data": None,
                    "error": {
                        "code": "UNKNOWN_TOOL",
                        "message": (
                            f"Unknown VoiceLab tool: {name}. "
                            "Available tools are: "
                            "analyze_symmetry, calculate_representation, "
                            "verify_representation, full_analysis."
                        ),
                    },
                }

            if name == "analyze_symmetry":
                return analyze_symmetry(
                    molecule=arguments.get(
                        "molecule",
                        "",
                    )
                )

            if name == "full_analysis":
                return analyze_molecule(
                    molecule=arguments.get(
                        "molecule",
                        "",
                    ),
                    basis=arguments.get(
                        "basis",
                        None,
                    ),
                )

            if name == "calculate_representation":
                return calculate_representation(
                    molecule=arguments.get(
                        "molecule",
                        "",
                    ),
                    basis=arguments.get(
                        "basis",
                        [],
                    ),
                    operations=arguments.get(
                        "operations",
                        [],
                    ),
                )

            if name == "verify_representation":
                return verify_representation(
                    molecule=arguments.get(
                        "molecule",
                        "",
                    ),
                    operations=arguments.get(
                        "operations",
                        [],
                    ),
                    representation_matrices=arguments.get(
                        "representation_matrices",
                        {},
                    ),
                    characters=arguments.get(
                        "characters",
                        {},
                    ),
                )

        except Exception as exc:
            logger.exception(
                "VoiceLab tool execution failed: %s",
                name,
            )

            return {
                "success": False,
                "tool": name,
                "data": None,
                "error": {
                    "code": "TOOL_EXECUTION_ERROR",
                    "message": str(exc),
                },
            }

    # ------------------------------------------------------------------
    # Event normalization
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_event(
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert AssemblyAI events into VoiceLab events."""

        event_type = event.get("type")

        if event_type == "session.ready":
            return {
                "type": "session",
                "state": "ready",
                "session_id": event.get("session_id"),
            }

        if event_type == "session.updated":
            return {
                "type": "session",
                "state": "updated",
            }

        if event_type == "input.speech.started":
            return {
                "type": "voice_state",
                "state": "listening",
            }

        if event_type == "input.speech.stopped":
            return {
                "type": "voice_state",
                "state": "processing",
            }

        if event_type == "transcript.user.delta":
            return {
                "type": "transcript",
                "role": "user",
                "text": event.get("text", ""),
                "final": False,
            }

        if event_type == "transcript.user":
            return {
                "type": "transcript",
                "role": "user",
                "text": event.get("text", ""),
                "final": True,
            }

        if event_type == "transcript.agent":
            return {
                "type": "transcript",
                "role": "assistant",
                "text": event.get("text", ""),
                "final": True,
                "interrupted": bool(
                    event.get("interrupted", False)
                ),
            }

        if event_type == "reply.started":
            return {
                "type": "voice_state",
                "state": "speaking",
                "reply_id": event.get("reply_id"),
            }

        if event_type == "reply.done":
            return {
                "type": "voice_state",
                "state": "idle",
                "status": event.get("status"),
            }

        if event_type == "tool.call":
            return {
                "type": "tool_call",
                "tool": event.get("name"),
                "call_id": event.get("call_id"),
                "arguments": event.get(
                    "arguments",
                    {},
                ),
            }

        if event_type == "session.error":
            return {
                "type": "error",
                "code": event.get("code"),
                "message": event.get("message"),
            }

        if event_type == "session.ended":
            return {
                "type": "session",
                "state": "ended",
            }

        return {
            "type": "unknown",
            "event": event,
        }

    # ------------------------------------------------------------------
    # Event loop
    # ------------------------------------------------------------------

    async def receive_events(
        self,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Receive and process AssemblyAI events.

        Automatically reconnects after transient failures.
        """

        while not self._intentional_close:
            if (
                self.websocket is None
                or not self.is_connected
            ):
                connected = await self.reconnect()

                if not connected:
                    yield {
                        "type": "error",
                        "code": "RECONNECT_FAILED",
                        "message": (
                            "Unable to reconnect to AssemblyAI "
                            "after the configured retry attempts."
                        ),
                    }
                    return

            try:
                async for event in (
                    self._receive_current_connection()
                ):
                    yield event

                if (
                    not self._intentional_close
                    and self.is_connected
                ):
                    self._mark_disconnected()

            except (
                websockets.ConnectionClosed,
                ConnectionError,
                OSError,
            ) as exc:
                if self._intentional_close:
                    return

                logger.warning(
                    "AssemblyAI WebSocket disconnected: %s",
                    exc,
                )

                self._mark_disconnected()

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                if self._intentional_close:
                    return

                logger.exception(
                    "Unexpected AssemblyAI event-loop error: %s",
                    exc,
                )

                self._mark_disconnected()

            if self._intentional_close:
                return

            connected = await self.reconnect()

            if not connected:
                yield {
                    "type": "error",
                    "code": "RECONNECT_FAILED",
                    "message": (
                        "AssemblyAI connection could not be restored."
                    ),
                }
                return

            yield {
                "type": "connection",
                "state": "reconnected",
                "session_id": self.assembly_session_id,
                "resumed": self.can_resume_session,
            }

    async def _receive_current_connection(
        self,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Process events from the currently connected WebSocket.
        """

        if self.websocket is None:
            raise ConnectionError(
                "AssemblyAI WebSocket is not connected."
            )

        async for raw_message in self.websocket:
            try:
                event = json.loads(raw_message)

            except json.JSONDecodeError:
                yield {
                    "type": "error",
                    "code": "INVALID_JSON",
                    "message": (
                        "Received invalid JSON from AssemblyAI."
                    ),
                }
                continue

            event_type = event.get("type")

            # ----------------------------------------------------------
            # Session ready
            # ----------------------------------------------------------

            if event_type == "session.ready":
                new_session_id = event.get(
                    "session_id"
                )

                if new_session_id:
                    self.assembly_session_id = (
                        new_session_id
                    )

                self.is_ready = True
                self.is_connected = True

                self._disconnect_monotonic = None
                self._reconnect_attempts = 0

                yield self.normalize_event(event)
                continue

            # ----------------------------------------------------------
            # Session error
            # ----------------------------------------------------------

            if event_type == "session.error":
                error_code = event.get("code")

                if error_code in SESSION_RESET_ERROR_CODES:
                    logger.warning(
                        "AssemblyAI session cannot be resumed: %s",
                        error_code,
                    )

                    self.assembly_session_id = None
                    self._disconnect_monotonic = None

                    yield {
                        "type": "session",
                        "state": "resume_failed",
                        "code": error_code,
                        "message": event.get("message"),
                    }

                    self._mark_disconnected()
                    await self._close_socket_only()

                    return

                yield self.normalize_event(event)
                continue

            # ----------------------------------------------------------
            # Tool call
            # ----------------------------------------------------------

            if event_type == "tool.call":
                tool_name = event.get("name")
                call_id = event.get("call_id")

                arguments = event.get(
                    "arguments",
                    {},
                )

                # DEBUG/DIAGNOSTIC:
                # Record the exact tool name and arguments received from
                # AssemblyAI before any VoiceLab tool is executed.
                logger.info(
                    "ASSEMBLYAI TOOL CALL: name=%s call_id=%s arguments=%s",
                    tool_name,
                    call_id,
                    arguments,
                )

                result = self.dispatch_tool(
                    name=tool_name,
                    arguments=arguments,
                )

                logger.info(
                    "ASSEMBLYAI TOOL RESULT: name=%s call_id=%s success=%s result=%s",
                    tool_name,
                    call_id,
                    result.get("success") if isinstance(result, dict) else None,
                    result,
                )

                # Store result for AssemblyAI protocol.
                self.pending_tool_results.append(
                    {
                        "call_id": call_id,
                        "result": result,
                    }
                )

                # IMPORTANT:
                # Also emit the actual completed tool result to
                # VoiceSession so ResearchSession is updated immediately.
                yield {
                    "type": "tool_result",
                    "tool": tool_name,
                    "call_id": call_id,
                    "result": result,
                }

                # Emit tool-call event for frontend status.
                yield self.normalize_event(event)

                continue

            # ----------------------------------------------------------
            # Reply complete
            # ----------------------------------------------------------

            if event_type == "reply.done":
                status = event.get("status")

                if status == "interrupted":
                    self.pending_tool_results.clear()

                elif self.pending_tool_results:
                    await self._send_pending_tool_results()

                yield self.normalize_event(event)
                continue

            # ----------------------------------------------------------
            # Session ended
            # ----------------------------------------------------------

            if event_type == "session.ended":
                self.is_ready = False
                self.is_connected = False

                self.assembly_session_id = None
                self._disconnect_monotonic = None

                yield self.normalize_event(event)
                return

            # ----------------------------------------------------------
            # Assistant audio
            # ----------------------------------------------------------

            if event_type == "reply.audio":
                audio_data = event.get("data")

                if audio_data:
                    yield {
                        "type": "audio",
                        "data": audio_data,
                    }

                continue

            # ----------------------------------------------------------
            # Other events
            # ----------------------------------------------------------

            yield self.normalize_event(event)

    async def _send_pending_tool_results(self) -> None:
        """
        Send accumulated tool results after reply.done.
        """

        if not self.pending_tool_results:
            return

        pending_results = list(
            self.pending_tool_results
        )

        self.pending_tool_results.clear()

        try:
            for pending in pending_results:
                result = pending["result"]

                if not isinstance(result, str):
                    result = json.dumps(result)

                await self._send(
                    {
                        "type": "tool.result",
                        "call_id": pending["call_id"],
                        "result": result,
                    }
                )

        except (
            websockets.ConnectionClosed,
            ConnectionError,
            OSError,
        ):
            self.pending_tool_results = (
                pending_results
                + self.pending_tool_results
            )

            self._mark_disconnected()
            raise

    # ------------------------------------------------------------------
    # Convenience runner
    # ------------------------------------------------------------------

    async def run(
        self,
        resume_session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Connect and continuously yield normalized events.
        """

        self._intentional_close = False

        if resume_session_id:
            self.assembly_session_id = resume_session_id

        try:
            connected = await self.reconnect()

            if not connected:
                yield {
                    "type": "error",
                    "code": "INITIAL_CONNECTION_FAILED",
                    "message": (
                        "Unable to establish an AssemblyAI "
                        "Voice Agent connection."
                    ),
                }
                return

            async for event in self.receive_events():
                yield event

        finally:
            if self._intentional_close:
                await self._close_socket_only()

            else:
                await self._close_socket_only()