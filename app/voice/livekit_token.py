"""LiveKit room token generation for the VoiceLab FastAPI app."""
from __future__ import annotations

import os
from datetime import timedelta

from livekit import api


def create_voice_token(room_name: str, identity: str) -> str:
    """Create a short-lived browser token for one VoiceLab research room."""

    token = (
        api.AccessToken(
            api_key=os.environ["LIVEKIT_API_KEY"],
            api_secret=os.environ["LIVEKIT_API_SECRET"],
        )
        .with_identity(identity)
        .with_name("VoiceLab Researcher")
        .with_ttl(timedelta(minutes=30))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name="voicelab",
                    )
                ],
            )
        )
        .to_jwt()
    )

    return token