#!/usr/bin/env sh
set -eu

: "${ASSEMBLYAI_API_KEY:?ASSEMBLYAI_API_KEY is required}"
: "${LIVEKIT_URL:?LIVEKIT_URL is required}"
: "${LIVEKIT_API_KEY:?LIVEKIT_API_KEY is required}"
: "${LIVEKIT_API_SECRET:?LIVEKIT_API_SECRET is required}"

exec python -m app.voice.livekit_agent start
