# VoiceLab — LiveKit migration

## New voice architecture

Browser -> LiveKit WebRTC -> LiveKit Agent -> AssemblyAI STT -> LLM -> TTS -> LiveKit audio

The existing deterministic science layer remains unchanged:

- `app/tools/symmetry.py`
- `app/tools/representation.py`
- `app/tools/verification.py`
- `app/tools/full_analysis.py`
- `app/science/`
- `app/agent/state.py`

## Install

```powershell
pip install -r requirements-livekit.txt
```

## Environment

Copy `.env.livekit.example` values into `.env`.

## Start the LiveKit agent worker

From the VoiceLab project root:

```powershell
python -m app.voice.livekit_agent dev
```

The worker registers as agent `voicelab`.

## Browser transport

The browser should receive a LiveKit room token from the FastAPI backend, connect to `LIVEKIT_URL`, and enable the microphone through LiveKit. Do not send PCM frames through the old `/ws/voice/{session_id}` transport in the LiveKit mode.

## Important

The existing AssemblyAI WebSocket implementation is intentionally left intact for rollback. Switch the frontend/backend routing only after the LiveKit path passes:

1. user speech -> AssemblyAI transcript
2. interruption/barge-in
3. full_analysis tool call
4. dynamic research state update
5. verification PASS
6. reconnect

No scientific implementation is duplicated in the LiveKit worker.


## Model stack (OpenAI-free)

- Transport/runtime: LiveKit Agents
- STT: AssemblyAI Universal-3.5 Pro
- LLM: Google Gemini 2.5 Flash Lite
- TTS: Google Gemini 3.1 Flash TTS Preview
- Science: existing VoiceLab Python tools (unchanged)

Required provider keys: LIVEKIT_URL/API_KEY/API_SECRET, ASSEMBLYAI_API_KEY, and GOOGLE_API_KEY. No OPENAI_API_KEY is used.
