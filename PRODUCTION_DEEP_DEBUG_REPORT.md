# VoiceLab — Deep Debug Audit

## Scope
Audited the BF3 Scientific Copilot production package across scientific math, state persistence, authentication, typed input, viewer actions, LiveKit/AssemblyAI bridge, vision endpoint, frontend syntax, Docker configuration, and staging/E2E checks.

## Findings fixed in this build

1. **Typed-command runtime NameError**
   - `app/main.py` used `asyncio.to_thread(...)` without importing `asyncio`.
   - Fixed and syntax-checked.

2. **Production startup could silently run without required security/provider configuration**
   - Added production startup validation for auth, LiveKit, AssemblyAI and Gemini configuration.
   - Enforces minimum production password/secret lengths.

3. **Authentication parser had an over-broad `Exception` tuple**
   - Replaced with explicit expected decoding/type errors.

4. **BF3 bootstrap swallowed registry failures**
   - Session creation now fails loudly if the canonical BF3 molecule cannot be loaded instead of creating an apparently valid empty viewer state.

5. **Auth tests were coupled to the optional LiveKit test dependency**
   - Added dependency-free authentication unit tests covering round-trip, tampering, wrong owner username and expiration.

## Verified scientific paths

- BF3 geometry: trigonal-planar, normalized B–F length.
- 12 registered D3h operations geometrically verified.
- Point group inferred from verified class signature: D3h.
- C4(z, 90°) is actually transformed and fails atom mapping.
- Full analysis returns PASS verification.

## Remaining staging-only gates

These cannot honestly be proven in an offline container:

- Real LiveKit browser WebRTC media.
- Real AssemblyAI microphone/TTS round trip.
- Real barge-in while TTS is playing.
- Real Gemini Vision request against staging credentials.
- Process restart/recovery against the deployed volume.

Run:

```bash
VOICE_LAB_BASE_URL=https://staging.example.com python scripts/staging_check.py --live
E2E_BASE_URL=https://staging.example.com python scripts/e2e_browser.py
```

## Important architecture note

The SQLite session object still uses read-modify-write JSON snapshots. This is adequate for the single-user hackathon flow but is not a full append-only transactional event store. For multi-user/high-concurrency production, move memory/audit events to an append-only table and use optimistic versioning/transactions for the mutable session state.
