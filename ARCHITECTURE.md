# VoiceLab Architecture

## System Overview

VoiceLab separates conversational intelligence from scientific computation.

```text
┌──────────────────────┐
│      User Voice      │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ AssemblyAI Voice     │
│ Agent / STT / Turns  │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ Agent Orchestration  │
│ Intent → Tool Call   │
│ State / Session      │
└──────────┬───────────┘
           ↓
┌─────────────────────────────────┐
│       Deterministic Science     │
│ Geometry normalization           │
│ Symmetry operations              │
│ Cartesian transformations        │
│ Matrix representations           │
│ Character calculations           │
│ Point-group resolution           │
│ Group-theory reduction           │
│ Geometric verification            │
└───────────────┬─────────────────┘
                ↓
┌──────────────────────────────┐
│ Interactive Scientific UI    │
│ Workspace / Analysis /       │
│ Verification / Representation│
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│ Research Replay              │
│ Auditable analysis timeline  │
└──────────────────────────────┘
```

## Core Components

### `app/voice/`

Real-time voice interaction, AssemblyAI integration, LiveKit session handling, and voice-session lifecycle.

### `app/agent/`

Agent state, scientific task coordination, session state, persistence, and system behavior.

### `app/science/`

Core molecular-symmetry implementation:

- molecular registry
- geometry normalization
- symmetry operations
- point-group definitions
- transformations
- characters
- group-theory reduction
- PubChem-assisted molecular data workflows

### `app/tools/`

Scientific operations exposed to the application/agent, including full analysis, representations, operation testing, verification, and vibrational analysis.

### `app/web/`

Interactive scientific workspace, analysis views, molecular visualization, result views, and Research Replay.

## Scientific Trust Model

VoiceLab separates **AI-generated intent** from **deterministic scientific evidence**.

```text
Natural language
      ↓
Structured scientific intent
      ↓
Deterministic computation
      ↓
Verification
      ↓
Scientific result
      ↓
Natural-language explanation
```

The language model is therefore not the sole source of numerical or mathematical truth.

## BF₃ Example

```text
BF₃
 ↓
D₃h
 ↓
12 symmetry operations
 ↓
Geometric verification
 ↓
Cartesian representation Γ(x,y,z)
 ↓
Character vector
 ↓
Irreducible-representation reduction
 ↓
Γ(x,y,z) = E′ + A₂″
```

## Persistence

The application includes persistent-state infrastructure with SQLite/PostgreSQL support.

## Security Boundary

Secrets belong in environment variables and are excluded from version control. Example environment templates are included; production credentials must be supplied separately.
