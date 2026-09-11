# VoiceLab Live Staging Checklist

## 0. Configuration
- [ ] `ENVIRONMENT=production` and `DEBUG=false`.
- [ ] Set `AUTH_USERNAME`, a long random `AUTH_PASSWORD`, and a 32+ byte `AUTH_SECRET`.
- [ ] Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
- [ ] Set `ASSEMBLYAI_API_KEY` and `GOOGLE_API_KEY`.
- [ ] Use HTTPS/WSS through the production reverse proxy.
- [ ] Verify `/app/data/voicelab_state.db` is on a persistent volume.

## 1. Authentication / ownership
- [ ] Anonymous `POST /api/sessions` returns `401`.
- [ ] Valid login sets an HttpOnly, SameSite=Strict cookie.
- [ ] Invalid credentials return `401`.
- [ ] A session cannot be read/reset/replayed by a different owner.
- [ ] Logout invalidates the browser session.
- [ ] Expired/tampered auth cookies are rejected.

## 2. FastAPI + persistence
- [ ] `/health` returns 200.
- [ ] Create a session and record molecule/analysis state.
- [ ] Restart FastAPI.
- [ ] Re-open the same session and confirm state, memory, and verification history remain.
- [ ] Confirm two simultaneous requests do not corrupt the SQLite file.

## 3. LiveKit
- [ ] Browser receives a short-lived token only after authentication/ownership check.
- [ ] Token room is exactly `voicelab-<session_id>`.
- [ ] Token identity is exactly `researcher-<session_id>`.
- [ ] Browser joins the expected room.
- [ ] Agent dispatch launches `voicelab`.
- [ ] Remote agent audio is audible after the user gesture.
- [ ] Browser microphone publishes successfully.

## 4. AssemblyAI
- [ ] Worker logs connection to AssemblyAI.
- [ ] `session.ready` arrives.
- [ ] User transcript arrives.
- [ ] Agent transcript and `reply.audio` arrive.
- [ ] Tool call is executed and result is returned only after `reply.done`.
- [ ] Provider errors surface as a visible VoiceLab error state.

## 5. Voice → Action
- [ ] Say `Analyze H2O` and confirm scientific state changes.
- [ ] Say `rotate left`, `zoom in`, `show atom labels`, `show element names`.
- [ ] Confirm viewer changes without changing scientific calculations.
- [ ] Confirm each action appears in replay memory.

## 6. Natural interruption
- [ ] Start a long agent response.
- [ ] Interrupt while TTS is speaking.
- [ ] Confirm stale audio stops immediately.
- [ ] Confirm interrupted turn does not send stale tool results.
- [ ] Confirm a subsequent user command works normally.

## 7. Gemini Screen Vision
- [ ] Capture a user-approved workspace screenshot.
- [ ] `/vision` returns structured JSON.
- [ ] Visible UI facts are grounded in the screenshot.
- [ ] Vision does not mutate scientific state.
- [ ] Missing/invalid/oversized screenshots fail cleanly.

## 8. Recovery
- [ ] Refresh browser during an active voice session.
- [ ] Confirm AssemblyAI resume/reconnect path is attempted when within its resume window.
- [ ] If resume is unavailable, confirm a fresh session is created cleanly.
- [ ] Confirm SQLite state survives FastAPI/worker restarts.
- [ ] Confirm replay still contains the last durable events.

## Automated checks

Safe local contract suite:

```bash
PYTHONPATH=. pytest -q
```

Provider/config smoke check without paid live calls:

```bash
python scripts/staging_check.py
```

Live staging provider check:

```bash
VOICE_LAB_BASE_URL=https://staging.example.com python scripts/staging_check.py --live
```

The live script checks configured provider reachability. Browser microphone, WebRTC media, and real interruption should still be exercised in the staging checklist because those depend on a real browser/audio device.

## 9. BF₃ Scientific Copilot demo gate
- [ ] New session opens with BF₃ loaded in trigonal-planar geometry.
- [ ] Say `Analyze this molecule`; confirm the agent resolves "this molecule" to the active BF₃ state.
- [ ] Confirm the engine verifies 12 operations and infers `D3h` from the verified operation-class signature.
- [ ] Confirm UI shows E, 2C₃, 3C₂′, σh, 2S₃, 3σv as verified.
- [ ] Say `Show me the C3 axis`; confirm the z-axis is visibly highlighted.
- [ ] Say `Show me the C2 axes`; confirm all three in-plane C₂′ axes are highlighted.
- [ ] Say `Why is sigma-h present?`; confirm the molecular plane is highlighted and the explanation is based on the verified transformation.
- [ ] Say `Test C4`; confirm a real 90° z-axis Cartesian transformation is executed and `C4 ✗ FAILED` is shown because the transformed F positions do not match the original atom set.
- [ ] Say `Explain the result`; confirm the response uses the latest verified state rather than inventing a new calculation.
- [ ] Confirm the visible Agent Trace progresses through state/calculation/verification/result/action without exposing private chain-of-thought.
- [ ] Force a UI-action failure in staging and confirm expected-vs-actual state is recorded and the recovery path can reset/retry.

## 10. Automated scientific + provider gates
```bash
PYTHONPATH=. pytest -q
VOICE_LAB_BASE_URL=https://staging.example.com python scripts/staging_check.py --live
```
The provider check must pass for FastAPI auth/session creation, LiveKit token issuance, AssemblyAI `session.ready`, and Gemini Vision. Real browser microphone, WebRTC audio, barge-in, screen capture permission, and UI recovery remain manual staging gates.
