"""
VoiceLab voice-session manager.

Responsibilities:
    - Create and manage an active research session.
    - Connect the browser/application to the AssemblyAI Voice Agent.
    - Forward microphone audio to AssemblyAI.
    - Forward normalized voice-agent events to the frontend.
    - Keep AssemblyAI reconnect/resume handling inside the voice layer.
    - Keep scientific state inside ResearchSession.

This module does NOT perform scientific calculations.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from app.agent.state import (
    ResearchSession,
    create_session,
    delete_session,
)
from app.voice.assemblyai_agent import AssemblyAIVoiceAgent
from app.science.molecule_registry import get_molecule


logger = logging.getLogger(__name__)


class VoiceSession:
    """
    Represents one active VoiceLab browser/voice session.

    A VoiceSession owns:
        - one ResearchSession
        - one AssemblyAIVoiceAgent
        - the event bridge between them
    """

    def __init__(
        self,
        research_session: ResearchSession | None = None,
        owner_id: str | None = None,
    ) -> None:
        self.research_session = (
            research_session
            if research_session is not None
            else create_session(owner_id=owner_id)
        )

        self.agent = AssemblyAIVoiceAgent()

        self._event_task: asyncio.Task | None = None
        self._closed = False

        self._event_queue: asyncio.Queue[
            dict[str, Any]
        ] = asyncio.Queue()

        self._tool_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        """Return the VoiceLab research-session ID."""
        return self.research_session.session_id

    @property
    def assembly_session_id(self) -> str | None:
        """Return the current AssemblyAI session ID."""
        return self.agent.assembly_session_id

    @property
    def is_connected(self) -> bool:
        """Return whether the AssemblyAI connection is active."""
        return self.agent.is_connected

    @property
    def is_ready(self) -> bool:
        """Return whether the AssemblyAI session is ready."""
        return self.agent.is_ready

    @property
    def is_closed(self) -> bool:
        """Return whether this VoiceSession has been closed."""
        return self._closed

    # ------------------------------------------------------------------
    # Start / connect
    # ------------------------------------------------------------------

    async def start(
        self,
        resume_assembly_session_id: str | None = None,
    ) -> None:
        """
        Start the voice session.

        If an AssemblyAI session ID is supplied, it is assigned BEFORE
        connecting so the AssemblyAI layer can actually attempt resume.

        Otherwise a fresh AssemblyAI session is created.
        """

        if self._closed:
            raise RuntimeError(
                "Cannot start a closed VoiceSession."
            )

        if (
            self._event_task is not None
            and not self._event_task.done()
        ):
            return

        try:
            # ----------------------------------------------------------
            # Set resume session ID BEFORE reconnect().
            # ----------------------------------------------------------

            if resume_assembly_session_id:
                self.agent.assembly_session_id = (
                    resume_assembly_session_id
                )

            elif self.agent.assembly_session_id:
                # Existing AssemblyAI session is intentionally retained.
                pass

            else:
                self.agent.assembly_session_id = None

            # ----------------------------------------------------------
            # Connect / reconnect.
            # ----------------------------------------------------------

            connected = await self.agent.reconnect(
                reset_session=(
                    resume_assembly_session_id is None
                    and self.agent.assembly_session_id is None
                )
            )

            if not connected:
                raise ConnectionError(
                    "Unable to connect to AssemblyAI Voice Agent."
                )

            # ----------------------------------------------------------
            # Start event bridge.
            # ----------------------------------------------------------

            self._event_task = asyncio.create_task(
                self._event_bridge(),
                name=f"voicelab-event-bridge-{self.session_id}",
            )

            # ----------------------------------------------------------
            # Send current state immediately.
            # ----------------------------------------------------------

            await self._queue_state_event()

        except Exception:
            logger.exception(
                "Failed to start VoiceSession %s",
                self.session_id,
            )
            raise

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    async def send_audio(
        self,
        audio: bytes,
    ) -> None:
        """
        Send microphone audio to AssemblyAI.

        The AssemblyAI layer handles reconnect automatically if the
        WebSocket has temporarily disconnected.
        """

        if self._closed:
            raise RuntimeError(
                "VoiceSession is closed."
            )

        if not isinstance(audio, bytes):
            raise TypeError(
                "audio must be bytes."
            )

        if not audio:
            return

        await self.agent.send_audio(audio)

    # ------------------------------------------------------------------
    # Event bridge
    # ------------------------------------------------------------------

    async def _event_bridge(self) -> None:
        """
        Consume normalized AssemblyAI events and push VoiceLab events
        into the frontend event queue.
        """

        try:
            async for event in self.agent.receive_events():
                if not isinstance(event, dict):
                    logger.warning(
                        "Ignoring non-dict voice event: %r",
                        event,
                    )
                    continue

                await self._handle_event(event)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.exception(
                "Voice event bridge failed for session %s",
                self.session_id,
            )

            await self._queue_event(
                {
                    "type": "error",
                    "code": "VOICE_EVENT_BRIDGE_ERROR",
                    "message": str(exc),
                }
            )

    async def _handle_event(
        self,
        event: dict[str, Any],
    ) -> None:
        """
        Handle one normalized AssemblyAI event.

        Scientific state is updated only from completed tool results.
        """

        event_type = event.get("type")

        # --------------------------------------------------------------
        # Session
        # --------------------------------------------------------------

        if event_type == "session":
            await self._handle_session_event(event)
            return

        # --------------------------------------------------------------
        # Connection
        # --------------------------------------------------------------

        if event_type == "connection":
            await self._queue_event(event)
            return

        # --------------------------------------------------------------
        # Tool call
        # --------------------------------------------------------------

        if event_type in {
            "tool_call",
            "tool.call",
        }:
            await self._handle_tool_call(event)
            return

        # --------------------------------------------------------------
        # Tool result
        # --------------------------------------------------------------

        if event_type in {
            "tool_result",
            "tool.result",
        }:
            await self._handle_tool_result(event)
            return

        # --------------------------------------------------------------
        # Explicit research state
        # --------------------------------------------------------------

        if event_type == "state":
            state = self._extract_state_from_event(event)

            if state is not None:
                await self._queue_state_event(state)
            else:
                await self._queue_event(event)

            return

        # --------------------------------------------------------------
        # Error
        # --------------------------------------------------------------

        if event_type == "error":
            await self._queue_event(event)
            return

        # --------------------------------------------------------------
        # Everything else
        # --------------------------------------------------------------

        await self._queue_event(event)

    # ------------------------------------------------------------------
    # Session event
    # ------------------------------------------------------------------

    async def _handle_session_event(
        self,
        event: dict[str, Any],
    ) -> None:
        state = str(
            event.get("state", "")
        ).lower()

        if state == "ready":
            assembly_session_id = event.get("session_id")

            if assembly_session_id:
                self.agent.assembly_session_id = (
                    assembly_session_id
                )

            await self._queue_event(
                {
                    "type": "session",
                    "state": "ready",
                    "session_id": self.session_id,
                    "assembly_session_id": (
                        self.agent.assembly_session_id
                    ),
                }
            )

            await self._queue_state_event()
            return

        await self._queue_event(event)

    # ------------------------------------------------------------------
    # Tool call
    # ------------------------------------------------------------------

    async def _handle_tool_call(
        self,
        event: dict[str, Any],
    ) -> None:
        """
        Forward tool-call status to frontend.

        A tool.call alone NEVER modifies scientific state.
        """

        tool_name = self._normalize_tool_name(event)

        call_id = event.get("call_id")

        if call_id is None:
            call_id = event.get("id")

        await self._queue_event(
            {
                "type": "tool_status",
                "tool": tool_name,
                "state": "running",
                "call_id": call_id,
            }
        )

    # ------------------------------------------------------------------
    # Tool result
    # ------------------------------------------------------------------

    async def _handle_tool_result(
        self,
        event: dict[str, Any],
    ) -> None:
        """
        Apply a completed tool result to ResearchSession and immediately
        publish the updated state to the frontend.
        """

        async with self._tool_lock:
            tool_name = self._normalize_tool_name(event)

            result = self._extract_tool_result(event)

            call_id = event.get("call_id")

            if call_id is None:
                call_id = event.get("id")

            # ----------------------------------------------------------
            # Apply scientific result.
            # ----------------------------------------------------------

            updated = self._apply_tool_result_to_state(
                tool_name,
                result,
            )

            # ----------------------------------------------------------
            # Tell frontend that tool completed.
            # ----------------------------------------------------------

            await self._queue_event(
                {
                    "type": "tool_status",
                    "tool": tool_name,
                    "state": (
                        "completed"
                        if updated
                        else "failed"
                    ),
                    "call_id": call_id,
                    "result": result,
                }
            )

            # ----------------------------------------------------------
            # Send authoritative ResearchSession state.
            # ----------------------------------------------------------

            if updated:
                await self._queue_state_event()

    # ------------------------------------------------------------------
    # Tool result extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tool_result(
        event: dict[str, Any],
    ) -> Any:
        """
        Extract result from different normalized event shapes.
        """

        if "result" in event:
            return event.get("result")

        if "data" in event:
            return {
                "success": True,
                "data": event.get("data"),
                "error": None,
            }

        return None

    # ------------------------------------------------------------------
    # Tool name normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_tool_name(
        event: dict[str, Any],
    ) -> str | None:
        """
        Normalize tool names from AssemblyAI/tool wrapper events.
        """

        tool = event.get("tool")

        if isinstance(tool, dict):
            tool = tool.get("name")

        if tool is None:
            tool = event.get("name")

        if not isinstance(tool, str):
            return None

        aliases = {
            "symmetry": "analyze_symmetry",
            "analyze_symmetry": "analyze_symmetry",
            "representation": "calculate_representation",
            "calculate_representation": "calculate_representation",
            "verification": "verify_representation",
            "verify_representation": "verify_representation",
            "bf3_analysis": "bf3_analysis",
            "full_analysis": "full_analysis",
        }

        return aliases.get(tool, tool)

    # ------------------------------------------------------------------
    # State synchronization
    # ------------------------------------------------------------------

    def _apply_tool_result_to_state(
        self,
        tool_name: str | None,
        result: Any,
    ) -> bool:
        """
        Apply completed tool result to ResearchSession.

        Returns True when a valid successful scientific result was
        synchronized.

        This method performs NO scientific calculations.
        """

        # --------------------------------------------------------------
        # Parse JSON-string result if necessary.
        # --------------------------------------------------------------

        if isinstance(result, str):
            try:
                result = json.loads(result)

            except (
                json.JSONDecodeError,
                TypeError,
            ):
                logger.warning(
                    "Could not decode tool result string."
                )
                return False

        if not isinstance(result, dict):
            return False

        # --------------------------------------------------------------
        # Some integrations wrap result again.
        # --------------------------------------------------------------

        if (
            "result" in result
            and isinstance(result.get("result"), dict)
        ):
            result = result.get("result")

        # --------------------------------------------------------------
        # Standard tool wrapper.
        # --------------------------------------------------------------

        success = result.get("success")

        if success is False:
            return False

        data = result.get("data")

        # --------------------------------------------------------------
        # Some normalized events expose data directly.
        # --------------------------------------------------------------

        if data is None:
            if any(
                key in result
                for key in (
                    "molecule",
                    "point_group",
                    "operations",
                    "representation_matrices",
                    "characters",
                    "status",
                )
            ):
                data = result

        if not isinstance(data, dict):
            return False

        # --------------------------------------------------------------
        # SYMMETRY
        # --------------------------------------------------------------

        if tool_name == "analyze_symmetry":
            molecule = data.get("molecule")
            point_group = data.get("point_group")
            operations = data.get("operations")

            if (
                not isinstance(molecule, str)
                or not isinstance(point_group, str)
                or not isinstance(operations, list)
            ):
                logger.warning(
                    "Invalid symmetry tool result."
                )
                return False

            self.research_session.update_symmetry(
                molecule=molecule,
                point_group=point_group,
                operations=operations,
            )

            return True

        # --------------------------------------------------------------
        # REPRESENTATION
        # --------------------------------------------------------------

        if tool_name == "calculate_representation":
            representation_matrices = data.get(
                "representation_matrices",
                {},
            )

            characters = data.get(
                "characters",
                {},
            )

            cartesian_matrices = data.get(
                "cartesian_matrices",
                {},
            )

            basis = data.get(
                "basis",
                [],
            )

            updated = False

            if isinstance(cartesian_matrices, dict):
                self.research_session.update_matrices(
                    cartesian_matrices
                )
                updated = True

            if isinstance(representation_matrices, dict):
                self.research_session.update_representation(
                    {
                        "basis": (
                            basis
                            if isinstance(basis, list)
                            else []
                        ),
                        "representation_matrices": (
                            representation_matrices
                        ),
                        "characters": (
                            characters
                            if isinstance(characters, dict)
                            else {}
                        ),
                    }
                )
                updated = True

            if isinstance(characters, dict):
                self.research_session.update_characters(
                    characters
                )
                updated = True

            return updated

        # --------------------------------------------------------------
        # BF3 COMPLETE ANALYSIS
        # --------------------------------------------------------------

        if tool_name == "bf3_analysis":
            updated = False

            # Symmetry
            molecule = data.get("molecule")
            point_group = data.get("point_group")
            operations = data.get("operations")

            if (
                isinstance(molecule, str)
                and isinstance(point_group, str)
                and isinstance(operations, list)
            ):
                self.research_session.update_symmetry(
                    molecule=molecule,
                    point_group=point_group,
                    operations=operations,
                )
                updated = True

            # Representation / matrices / characters
            representation = data.get("representation")

            if isinstance(representation, dict):
                cartesian_matrices = representation.get(
                    "cartesian_matrices",
                    {},
                )
                representation_matrices = representation.get(
                    "representation_matrices",
                    {},
                )
                characters = representation.get(
                    "characters",
                    {},
                )
                basis = representation.get(
                    "basis",
                    [],
                )

                if isinstance(cartesian_matrices, dict):
                    self.research_session.update_matrices(
                        cartesian_matrices
                    )
                    updated = True

                if isinstance(representation_matrices, dict):
                    self.research_session.update_representation(
                        {
                            "basis": (
                                basis
                                if isinstance(basis, list)
                                else []
                            ),
                            "representation_matrices": (
                                representation_matrices
                            ),
                            "characters": (
                                characters
                                if isinstance(characters, dict)
                                else {}
                            ),
                        }
                    )
                    updated = True

                if isinstance(characters, dict):
                    self.research_session.update_characters(
                        characters
                    )
                    updated = True

            # Verification
            verification = data.get("verification")

            if isinstance(verification, dict):
                self.research_session.update_verification(
                    verification
                )
                updated = True

            return updated

        # --------------------------------------------------------------
        # FULL ANALYSIS (registry-driven, any molecule/point group)
        # --------------------------------------------------------------

        if tool_name == "full_analysis":
            updated = False

            molecule_info = data.get("molecule")
            point_group = data.get("point_group")
            operations = data.get("operations")

            molecule_id = (
                molecule_info.get("id")
                if isinstance(molecule_info, dict)
                else molecule_info
            )

            if (
                isinstance(molecule_id, str)
                and isinstance(point_group, str)
                and isinstance(operations, list)
            ):
                self.research_session.update_symmetry(
                    molecule=molecule_id,
                    point_group=point_group,
                    operations=operations,
                )
                updated = True

            representation = data.get("representation")

            if isinstance(representation, dict):
                cartesian_matrices = representation.get(
                    "cartesian_matrices",
                    {},
                )
                representation_matrices = representation.get(
                    "representation_matrices",
                    {},
                )
                characters = representation.get(
                    "characters",
                    {},
                )
                basis = representation.get(
                    "basis",
                    [],
                )

                if isinstance(cartesian_matrices, dict):
                    self.research_session.update_matrices(
                        cartesian_matrices
                    )
                    updated = True

                if isinstance(representation_matrices, dict):
                    self.research_session.update_representation(
                        {
                            "basis": (
                                basis
                                if isinstance(basis, list)
                                else []
                            ),
                            "representation_matrices": (
                                representation_matrices
                            ),
                            "characters": (
                                characters
                                if isinstance(characters, dict)
                                else {}
                            ),
                        }
                    )
                    updated = True

                if isinstance(characters, dict):
                    self.research_session.update_characters(
                        characters
                    )
                    updated = True

            group_theory = data.get("group_theory")

            if isinstance(group_theory, dict):
                self.research_session.update_reduction(
                    group_theory
                )
                updated = True

            verification = data.get("verification")

            if isinstance(verification, dict):
                self.research_session.update_verification(
                    verification
                )
                updated = True

            return updated

        # --------------------------------------------------------------
        # VERIFICATION
        # --------------------------------------------------------------

        if tool_name == "verify_representation":
            status = data.get("status")
            checks = data.get("checks")
            errors = data.get("errors")

            if (
                status is None
                and checks is None
                and errors is None
            ):
                logger.warning(
                    "Invalid verification tool result."
                )
                return False

            self.research_session.update_verification(
                data
            )

            return True

        logger.warning(
            "Unknown tool result received: %s",
            tool_name,
        )

        return False

    # ------------------------------------------------------------------
    # State event
    # ------------------------------------------------------------------

    async def _queue_state_event(
        self,
        state: dict[str, Any] | None = None,
    ) -> None:
        """
        Put the authoritative ResearchSession state into the frontend
        event queue.
        """

        if state is None:
            state = self.research_session.to_dict()

        await self._queue_event(
            {
                "type": "state",
                "state": state,
            }
        )

    # ------------------------------------------------------------------
    # Generic queue helper
    # ------------------------------------------------------------------

    async def _queue_event(
        self,
        event: dict[str, Any],
    ) -> None:
        if not isinstance(event, dict):
            return

        await self._event_queue.put(event)

    # ------------------------------------------------------------------
    # State extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_state_from_event(
        event: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Extract ResearchSession state from a state event.
        """

        state = event.get("state")

        if not isinstance(state, dict):
            return None

        if (
            "research" in state
            and isinstance(state.get("research"), dict)
        ):
            return state.get("research")

        return state

    # ------------------------------------------------------------------
    # Event consumption
    # ------------------------------------------------------------------

    async def events(
        self,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Yield normalized events for the frontend.
        """

        while not self._closed:
            try:
                event = await self._event_queue.get()

            except asyncio.CancelledError:
                raise

            yield event

    async def next_event(
        self,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve one queued event.

        Returns None if the optional timeout expires.
        """

        if timeout is None:
            return await self._event_queue.get()

        try:
            return await asyncio.wait_for(
                self._event_queue.get(),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            return None

    # ------------------------------------------------------------------
    # Research state
    # ------------------------------------------------------------------

    def get_state(
        self,
    ) -> dict[str, Any]:
        """
        Return the current authoritative research state.
        """

        return self.research_session.to_dict()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def close(
        self,
        end_assembly_session: bool = False,
    ) -> None:
        """
        Close the VoiceSession.

        By default, close only the local AssemblyAI socket.

        Set end_assembly_session=True when the research session is
        explicitly finished.
        """

        if self._closed:
            return

        self._closed = True

        # --------------------------------------------------------------
        # Stop event bridge.
        # --------------------------------------------------------------

        if self._event_task is not None:
            current_task = asyncio.current_task()

            if self._event_task is not current_task:
                self._event_task.cancel()

                try:
                    await self._event_task

                except asyncio.CancelledError:
                    pass

            self._event_task = None

        # --------------------------------------------------------------
        # AssemblyAI shutdown.
        # --------------------------------------------------------------

        if end_assembly_session:
            await self.agent.end_session()

        else:
            await self.agent._close_socket_only()

        # --------------------------------------------------------------
        # Remove research session.
        # --------------------------------------------------------------

        delete_session(self.session_id)


# ----------------------------------------------------------------------
# Active VoiceSession registry
# ----------------------------------------------------------------------

_active_voice_sessions: dict[
    str,
    VoiceSession,
] = {}


def create_voice_session(owner_id: str | None = None) -> VoiceSession:
    """
    Create and register a new VoiceSession.
    """

    research_session = create_session(owner_id=owner_id)
    # BF3 is the canonical hackathon demo molecule. The underlying session
    # contract remains registry-driven, so changing the demo does not require
    # frontend molecule logic.
    definition = get_molecule("BF3")
    research_session.molecule = definition.molecule_id
    research_session.molecule_data = {
        "id": definition.molecule_id,
        "name": definition.name,
        "formula": definition.formula,
        "point_group": None,
        "coordinates": definition.coordinates,
        "bonds": getattr(definition, "bonds", []),
    }
    research_session.append_memory({"ts": __import__("time").time(), "kind": "state", "stage": "molecule", "message": "BF3 demo molecule loaded"})

    voice_session = VoiceSession(
        research_session=research_session,
        owner_id=owner_id,
    )

    _active_voice_sessions[
        voice_session.session_id
    ] = voice_session

    return voice_session


def get_voice_session(
    session_id: str,
) -> VoiceSession | None:
    """
    Return an active VoiceSession by research-session ID.
    """

    return _active_voice_sessions.get(session_id)


def require_voice_session(
    session_id: str,
) -> VoiceSession:
    """
    Return an active VoiceSession or raise KeyError.
    """

    voice_session = get_voice_session(session_id)

    if voice_session is None:
        raise KeyError(
            f"Voice session not found: {session_id}"
        )

    return voice_session


async def close_voice_session(
    session_id: str,
    end_assembly_session: bool = False,
) -> bool:
    """
    Close and unregister an active VoiceSession.

    Returns True if the session existed.
    """

    voice_session = _active_voice_sessions.pop(
        session_id,
        None,
    )

    if voice_session is None:
        return False

    await voice_session.close(
        end_assembly_session=end_assembly_session,
    )

    return True


def active_voice_session_count() -> int:
    """
    Return the number of currently registered voice sessions.
    """

    return len(_active_voice_sessions)