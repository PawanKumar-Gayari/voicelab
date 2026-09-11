# VoiceLab — BF₃ Scientific Copilot Demo

## Winning loop

`VOICE → VISION → UNDERSTAND → ACT → CALCULATE → VERIFY → EXPLAIN → RECOVER`

### 1. Start
A new research session loads BF₃ from the Molecule Registry. The geometry is trigonal planar with B at the origin and three equivalent F atoms at 120° intervals in the xy-plane.

### 2. Voice demo
Say:
- **Analyze this molecule.**
- **Show me the C3 axis.**
- **Show me the C2 axes.**
- **Why is sigma-h present?**
- **Test C4.**
- **Explain the result.**

The phrase "this molecule" resolves against the current persisted workspace state.

### 3. Scientific authority
The deterministic engine builds Cartesian matrices using `r' = M r`, transforms every atom, and performs element-preserving bijective coordinate matching. The point group is inferred from the verified operation-class signature and then cross-checked by the representation verification pipeline.

For BF₃, the verified operation set is:
- E
- 2C₃
- 3C₂′
- σh
- 2S₃
- 3σv

The resulting point group is **D3h**.

### 4. Negative proof
`Test C4` constructs a 90° rotation about z and tests it against the actual coordinates. It is expected to fail because the transformed F positions do not map onto the original F positions. The UI reports the failure and shows the actual transformation matrix/mapping in the trace data.

### 5. Visual actions
The viewer can highlight the C₃ axis, all C₂′ axes, and σh. These actions are visual-only and do not mutate scientific calculations.

### 6. Agent trace
The UI exposes concise status stages only:
`STATE → CALCULATION → VERIFICATION → RESULT → ACTION`.
Private chain-of-thought is never displayed.

### 7. Recovery
Browser viewer actions report actual viewer state back to the session. This creates a durable expected/actual audit trail for recovery and replay. A production staging test should deliberately induce a failed UI action and verify reset/retry handling.
