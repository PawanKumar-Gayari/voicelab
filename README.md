# VoiceLab — AI Scientific Copilot for Molecular Symmetry

> **Most voice agents can talk. VoiceLab can calculate and verify.**

VoiceLab is a voice-first scientific copilot that turns natural-language or voice requests into deterministic molecular-symmetry analysis. It combines an AI voice workflow with computational chemistry tools, symmetry operations, matrix representations, group theory, and verification.

Built for the **AssemblyAI Voice Agent Hackathon**.

## Problem

Scientific software often requires users to know commands, workflows, and mathematical procedures before they can ask a question. Generic voice assistants can explain science conversationally, but their answers are not necessarily backed by executable scientific calculations.

**VoiceLab connects the two.**

Example:

> “Analyze BF₃ and tell me its point group.”

VoiceLab interprets the request, runs the scientific workflow, verifies the result, and presents computational evidence.

## Key Features

- **Voice-first interaction** — natural-language and voice scientific requests.
- **Molecular symmetry analysis** — implemented workflows including H₂O, NH₃, and BF₃.
- **Deterministic computation** — geometry normalization, symmetry operations, Cartesian transformations, matrices, characters, point-group resolution, and group-theory reduction.
- **Geometric verification** — generated operations are checked against molecular geometry.
- **Cartesian representation** — BF₃/D₃h gives `Γ(x,y,z) = E′ + A₂″`.
- **Research Replay** — an auditable scientific workflow rather than only a final answer.

## Demo Result

```text
Point Group:  D₃h
Operations:   12
Verification: 12 / 12 PASS
Γ(x,y,z):     E′ + A₂″
```

## Architecture

```text
User Voice
    ↓
AssemblyAI Voice Workflow
    ↓
Scientific Intent / Agent Orchestration
    ↓
Deterministic Science Layer
    ├── Molecular geometry
    ├── Symmetry operations
    ├── Transformations / matrices
    ├── Characters
    ├── Point-group resolution
    ├── Group-theory reduction
    └── Verification
    ↓
Interactive Scientific Workspace
    ↓
Research Replay / Audit Trail
```

**Design principle: AI orchestrates. Science computes.**

See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Demo Flow

1. Speak: **“Analyze BF₃ and tell me its point group.”**
2. VoiceLab converts the request into a scientific task.
3. The scientific pipeline computes molecular symmetry.
4. Generated operations are geometrically verified.
5. Cartesian representation and characters are calculated.
6. Group-theory reduction produces the result.
7. Research Replay exposes the workflow and evidence.

See [`DEMO.md`](DEMO.md).

## Quick Start

Requirements: Python 3.10+, Node.js, Git, AssemblyAI API key, and LiveKit configuration.

```bash
git clone https://github.com/PawanKumar-Gayari/voicelab.git
cd voicelab

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Add the required API/configuration values to `.env`.

Start the web application:

```bash
./start-production.sh
```

Start the voice agent:

```bash
./start-voice-agent.sh
```

For Windows development, see [`README_WINDOWS_SAFE.md`](README_WINDOWS_SAFE.md).

## Testing

```bash
pytest -q
```

The repository includes scientific regression, symmetry, representation, verification, persistence, and voice-flow coverage.

## Project Structure

```text
voicelab/
├── app/
│   ├── agent/          # Agent state and orchestration
│   ├── science/        # Molecular symmetry and group theory
│   ├── tools/          # Scientific analysis tools
│   ├── voice/          # AssemblyAI / LiveKit voice workflow
│   ├── report/         # Research/report generation
│   └── web/            # Interactive workspace
├── tests/              # Scientific and application tests
├── scripts/            # Migration and verification utilities
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Technology

- Python
- AssemblyAI
- LiveKit
- JavaScript / HTML / CSS
- NumPy / scientific Python tooling
- SQLite / PostgreSQL support
- GitHub

## Why VoiceLab?

VoiceLab is **not intended to be a generic chemistry chatbot**.

Its core loop is:

```text
VOICE
  ↓
AI AGENT
  ↓
SCIENTIFIC COMPUTATION
  ↓
MATHEMATICAL REPRESENTATION
  ↓
VERIFICATION
  ↓
AUDITABLE RESULT
```

The AI layer handles conversational interaction and orchestration. The scientific layer performs the underlying mathematical and computational operations.

## Limitations

VoiceLab is a focused scientific prototype rather than a complete computational-chemistry platform.

- Molecular and point-group coverage is limited to implemented workflows.
- Complex geometries may require additional normalization and symmetry handling.
- Results depend on the quality and validity of supplied molecular geometry.
- The current implementation focuses on molecular symmetry and related representations, not broad quantum-chemistry calculations.
- Voice interaction depends on external API/network availability.
- Results should be independently validated before use in production scientific decision-making.

See [`LIMITATIONS.md`](LIMITATIONS.md).

## Links

- **Live app:** https://voicelab.aspirantveda.in/
- **Source:** https://github.com/PawanKumar-Gayari/voicelab

## One-line Pitch

> **VoiceLab is an AI scientific copilot that lets researchers speak a molecular-symmetry problem and receive a computed, verified, and auditable scientific result.**
