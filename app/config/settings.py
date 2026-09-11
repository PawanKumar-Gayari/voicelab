"""
VoiceLab application configuration.

All environment-dependent settings are centralized here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


# Load variables from .env when running locally.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """
    Application settings loaded from environment variables.
    """

    # Application
    app_name: str = os.getenv(
        "APP_NAME",
        "VoiceLab",
    )

    app_host: str = os.getenv(
        "APP_HOST",
        "127.0.0.1",
    )

    app_port: int = int(
        os.getenv(
            "APP_PORT",
            "8000",
        )
    )

    # AssemblyAI
    assemblyai_api_key: str = os.getenv(
        "ASSEMBLYAI_API_KEY",
        "",
    )

    # Environment
    environment: str = os.getenv(
        "ENVIRONMENT",
        "development",
    )

    debug: bool = os.getenv(
        "DEBUG",
        "true",
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


settings = Settings()


def validate_settings() -> None:
    """
    Validate required application configuration.

    The AssemblyAI key is required when the voice-agent layer is used.
    Scientific calculation modules do not require it.
    """
    if not settings.assemblyai_api_key.strip():
        raise ValueError(
            "ASSEMBLYAI_API_KEY is not configured. "
            "Add it to your .env file before starting the voice agent."
        )