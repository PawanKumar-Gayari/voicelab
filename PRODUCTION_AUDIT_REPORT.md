# VoiceLab Production Deep Audit

## Executive result

The deterministic scientific suite passes **80/80** tests, Python compilation passes, and the main workspace JavaScript files pass syntax checks.

This audit also found gaps that the existing 80 tests did not cover. The most important ones were fixed in this package:

1. **Container persistence path** — fixed. Docker's `/app/data` volume could be unused when `VOICELAB_DB_PATH` was omitted. The state layer now defaults to `/app/data/voicelab_state.db` when that directory exists.
2. **Typed molecule resolution** — fixed. The typed-command endpoint previously fell back to the first registered molecule if the requested molecule was not actually parsed. It now resolves an explicitly named registry molecule, rejects ambiguity, and only falls back to the active molecule when the command omits a molecule.

## Findings that remain architectural / need live production validation

### High: cross-process state write races
FastAPI and the LiveKit worker both mutate the same serialized SQLite row. The current pattern is read/modify/write of the whole `ResearchSession` JSON document. Concurrent mutations can theoretically overwrite fields written by the other process, including replay-memory events. This is the biggest remaining reliability gap.

Recommended production fix: move high-frequency mutable event data into append-only SQLite tables and use transactional updates for scientific state fields, instead of replacing the entire JSON blob.

### Medium: Replay is an audit timeline, not deterministic execution replay
The `/replay` endpoint currently returns stored events and verification records. It does **not** re-execute the tool calls or reproduce the UI state frame-by-frame. The UI label "Replay" is therefore best understood as "session timeline" until true event-sourced replay is implemented.

### Medium: Screen Vision is observe-only, not an action agent
The vision endpoint intentionally analyzes an approved screen capture and returns suggested actions. It does not execute those suggestions. This is safer, but it means "Screen Vision + UI Understanding" is not yet a closed-loop vision-to-action agent.

### Medium: no application authentication/authorization
Session APIs, replay, report, vision, and LiveKit token issuance are protected only by possession of a session UUID. There is no user authentication or ownership check. This is acceptable for a controlled hackathon deployment but is not sufficient for a multi-user public production service.

### Medium: production runtime needs real integration testing
The repository's unit tests do not establish that a real browser, LiveKit Cloud, AssemblyAI Voice Agent, Gemini Vision, microphone permission flow, browser autoplay, and reconnect/resume behavior all work together. Those require a live staging run with real credentials.

### Medium: duplicate legacy voice architecture
`app/voice/session.py` + `app/voice/assemblyai_agent.py` coexist with the direct LiveKit/AssemblyAI bridge in `app/voice/livekit_agent.py`. The two paths create maintenance risk and can diverge in behavior. A final cleanup should choose one authoritative runtime path and retire the unused compatibility path after migration tests.

### Low: registry currently contains only two molecules
The architecture is registry-driven and supports adding more modules automatically, but the current package actually discovers only the molecule modules present in `app/science/molecules/`. User-facing copy must not imply NH3/CH4/C2H4 are currently registered unless those modules are added.

## Feature-by-feature verdict

| Feature | Static/unit status | Verdict |
|---|---|---|
| Voice → Action | Tool schemas, deterministic dispatch, browser events present | Strong; live integration still required |
| Screen Vision + UI Understanding | Screenshot capture + Gemini analysis present | Strong observe-only implementation; not closed-loop action |
| Self-Verification | Independent verification tool + PASS/FLAG semantics | Strong deterministic gate |
| Natural Interruption | AssemblyAI interrupted state clears pending audio/tool results | Strong protocol handling; live test required |
| Agent Memory | Durable SQLite timeline | Present; concurrency race remains |
| Replay | Timeline endpoint/UI | Present, but not true execution replay |
| Typed Input | Shared deterministic tool path | Fixed in this audit |
| Molecule Viewer | Registry-fed geometry + viewer actions | Strong architecture; live browser test required |

## Validation performed

- `PYTHONPATH=. pytest -q` → **80 passed**
- `python -m compileall -q app` → passed
- `node --check app/web/static/js/workspace.js` → passed
- `node --check app/web/static/js/molecule_viewer.js` → passed

## Recommended final staging checklist

1. Start web + voice-agent containers with real staging credentials.
2. Open a fresh session from Home and confirm the session ID is preserved.
3. Confirm AssemblyAI `session.ready` and greeting audio.
4. Test voice → analysis → molecule rendering → verification.
5. Interrupt TTS while it is speaking and confirm stale audio stops.
6. Test typed and voice commands concurrently.
7. Test rotate/zoom/labels/element-name viewer actions by voice and typing.
8. Test browser refresh/reconnect and confirm memory/state survive.
9. Test Screen Vision permission and Gemini response.
10. Test report/result page with PASS and FLAG states.
11. Verify SQLite file is actually inside the persistent `/app/data` volume.
