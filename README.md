# VoiceLab — AI Scientific Copilot for Molecular Symmetry

> **Most voice agents can talk. VoiceLab can calculate and verify.**

VoiceLab is a voice-first scientific copilot that turns natural-language or voice requests into deterministic molecular-symmetry analysis.

Instead of treating a language model as the source of scientific truth, VoiceLab connects conversational AI with computational chemistry workflows that generate symmetry operations, matrix representations, characters, group-theory reductions, and geometric verification.

Built for the **AssemblyAI Voice Agent Hackathon**.

---

## Problem

Scientific software often requires users to know commands, workflows, and mathematical procedures before they can ask a question.

Generic voice assistants have the opposite problem: they can explain science conversationally, but their answers are not necessarily backed by an executable scientific calculation.

**VoiceLab connects the two.**

A user can simply say:

> **“Analyze BF₃ and tell me its point group.”**

VoiceLab interprets the request, runs the scientific workflow, verifies the result, and presents the computational evidence.

---

## Key Features

### 🎙️ Voice-first scientific interaction

Natural-language and voice requests are converted into structured scientific tasks through the voice-agent workflow.

### 🧪 Molecular symmetry analysis

Implemented molecular workflows include examples such as:

- H₂O
- NH₃
- BF₃

The scientific layer supports molecular geometry, symmetry operations, point-group resolution, representations, and verification.

### 📐 Deterministic scientific computation

VoiceLab performs computational analysis rather than relying only on generated explanations.

The workflow can include:

- Molecular geometry normalization
- Symmetry-element identification
- Symmetry-operation generation
- Cartesian transformations
- Matrix representations
- Character calculations
- Point-group resolution
- Group-theory reduction
- Geometric verification

### 🧬 PubChem molecular-data workflows

VoiceLab includes PubChem-related components for molecular structure/data workflows, including:

- Molecular structure retrieval
- Candidate resolution
- Geometry normalization
- Principal-axis handling
- Molecular-data caching
- Fallback workflows

These molecular-data workflows feed the scientific analysis pipeline.

### 🧊 3D molecular visualization

The interactive workspace uses **3Dmol.js** for 3D molecular visualization.

This allows users to inspect molecular structures alongside the computed symmetry analysis rather than receiving only text output.

### ✅ Scientific verification

Generated symmetry operations are checked against molecular geometry.

Representative BF₃ analysis:

```text
12 symmetry operations
12 / 12 verified
PASS
```

### 📊 Cartesian representation

For the Cartesian basis `{x, y, z}`, VoiceLab calculates the representation and reduces it against the relevant character table.

Example:

```text
BF₃
Point Group: D₃h

Γ(x,y,z) = E′ + A₂″
```

### 🔬 Research Replay

Research Replay presents the analysis as an auditable sequence of scientific events.

Instead of showing only:

```text
BF₃ → D₃h
```

VoiceLab can expose the workflow:

```text
Request
  ↓
Molecular data
  ↓
Geometry
  ↓
Symmetry operations
  ↓
Verification
  ↓
Matrices / characters
  ↓
Representation reduction
  ↓
Scientific result
```

---

## Demo Result

A representative BF₃ analysis produces:

```text
Molecule:      BF₃
Point Group:   D₃h
Operations:    12
Verification:  12 / 12 PASS
Γ(x,y,z):      E′ + A₂″
```

The important distinction is that the final answer is accompanied by computational evidence and verification.

---

# Architecture

```text
                         ┌─────────────────────┐
                         │      User Voice     │
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │ AssemblyAI Voice    │
                         │ Agent / STT / Turns │
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │ Scientific Intent   │
                         │ / Agent Orchestration│
                         └──────────┬──────────┘
                                    ↓
                  ┌──────────────────────────────────┐
                  │       Molecular Data Layer       │
                  │                                  │
                  │ PubChem workflows                 │
                  │ Molecular registry                │
                  │ Geometry normalization            │
                  │ Principal-axis handling            │
                  │ Cache / fallback                  │
                  └────────────────┬─────────────────┘
                                   ↓
                  ┌──────────────────────────────────┐
                  │       3D Visualization            │
                  │             3Dmol.js              │
                  └────────────────┬─────────────────┘
                                   ↓
                  ┌──────────────────────────────────┐
                  │      Deterministic Science        │
                  │                                  │
                  │ Symmetry operations                │
                  │ Transformations / matrices        │
                  │ Characters                        │
                  │ Point-group resolution             │
                  │ Group-theory reduction             │
                  │ Geometric verification             │
                  └────────────────┬─────────────────┘
                                   ↓
                         ┌─────────────────────┐
                         │ Scientific Workspace│
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │  Research Replay    │
                         │   / Audit Trail     │
                         └─────────────────────┘
```

### Design principle

> **AI orchestrates. Science computes.**

The AI/voice layer handles conversational interaction and scientific intent.

The scientific layer performs the underlying mathematical and computational operations.

---

## Scientific Trust Model

VoiceLab deliberately separates **AI-generated intent** from **deterministic scientific evidence**.

```text
Natural language
      ↓
Structured scientific intent
      ↓
Molecular data / geometry
      ↓
Deterministic computation
      ↓
Verification
      ↓
Scientific result
      ↓
Natural-language explanation
```

This design reduces reliance on a language model for numerical and mathematical truth.

---

# Demo Flow

## 1. Speak a scientific request

> **“Analyze BF₃ and tell me its point group.”**

## 2. Intent is interpreted

The voice agent converts the spoken request into a structured molecular-symmetry task.

## 3. Molecular information is prepared

Molecular structure/data workflows provide the geometry required by the scientific pipeline.

## 4. Symmetry is computed

VoiceLab determines the molecular symmetry and generates the corresponding symmetry operations.

## 5. Operations are verified

The generated operations are tested against the molecular geometry.

Example:

```text
Point Group:  D₃h
Operations:   12
Verification: 12 / 12 PASS
```

## 6. Group theory is calculated

VoiceLab constructs the Cartesian representation and calculates its characters.

For BF₃:

```text
Γ(x,y,z) = E′ + A₂″
```

## 7. Research Replay

The complete workflow can be inspected through the Research Replay interface.

---

# Molecular Data & Visualization

VoiceLab combines molecular data, visualization, and mathematical symmetry analysis.

```text
PubChem / Molecular Data
          ↓
Molecular Structure
          ↓
Geometry Normalization
          ↓
3Dmol.js Visualization
          ↓
Symmetry Computation
          ↓
Matrix / Character Representation
          ↓
Verification
          ↓
Research Replay
```

This gives the user both:

1. **visual understanding** of the molecular structure, and
2. **computational evidence** for the symmetry result.

---

# Technology

- **Python** — scientific computation and backend services
- **AssemblyAI** — voice-agent / speech interaction
- **gemini-ai** - For explanation of concept for group theory 
- **LiveKit** — real-time voice infrastructure
- **PubChem** — molecular structure/data workflows
- **3Dmol.js** — interactive 3D molecular visualization
- **NumPy / scientific Python tooling** — computational mathematics
- **JavaScript / HTML / CSS** — interactive scientific workspace
- **SQLite / PostgreSQL** — application state/persistence support
- **GitHub** — source control and collaboration

---

# Quick Start

## Requirements

- Python 3.10+
- Node.js
- Git
- AssemblyAI API key
- LiveKit configuration for the voice workflow

## Clone

```bash
git clone https://github.com/PawanKumar-Gayari/voicelab.git
cd voicelab
```

## Create Python environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## Install dependencies

```bash
pip install -r requirements.txt
```

## Configure environment

```bash
cp .env.example .env
```

Add the required API and service configuration values to `.env`.

**Do not commit `.env` or production credentials.**

## Start the web application

```bash
./start-production.sh
```

## Start the voice agent

```bash
./start-voice-agent.sh
```

For Windows development, see:

[`README_WINDOWS_SAFE.md`](README_WINDOWS_SAFE.md)

---

# Testing

Run the complete test suite:

```bash
pytest -q
```

The repository contains coverage for areas including:

- Molecular symmetry
- Point groups
- Transformations
- Representations
- Character/reduction workflows
- Geometric verification
- Molecular registry
- Persistence contracts
- Voice-flow smoke tests
- Scientific regression cases

---

# Project Structure

```text
voicelab/
├── app/
│   ├── agent/          # Agent state and orchestration
│   ├── science/        # Molecular symmetry and group theory
│   ├── tools/          # Scientific analysis tools
│   ├── voice/          # AssemblyAI / LiveKit voice workflow
│   ├── report/         # Research/report generation
│   └── web/             # Interactive scientific workspace
├── tests/               # Scientific and application tests
├── scripts/             # Migration and verification utilities
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

# Why VoiceLab?

VoiceLab is **not intended to be a generic chemistry chatbot**.

Its core loop is:

```text
VOICE
  ↓
AI AGENT
  ↓
MOLECULAR DATA
  ↓
SCIENTIFIC COMPUTATION
  ↓
MATHEMATICAL REPRESENTATION
  ↓
VERIFICATION
  ↓
AUDITABLE RESULT
```

The project demonstrates a different model for scientific voice agents:

> **Use AI to understand and orchestrate the scientific task, but use deterministic computational methods to establish the scientific result.**

---

# What Makes the Demo Interesting?

A generic voice assistant might answer:

> “BF₃ belongs to the D₃h point group.”

VoiceLab goes further.

It can show:

```text
BF₃
  ↓
D₃h
  ↓
12 symmetry operations
  ↓
12 / 12 verified
  ↓
Cartesian character representation
  ↓
Γ(x,y,z) = E′ + A₂″
  ↓
Research Replay
```

The result is therefore presented as a **scientific workflow**, not simply a generated sentence.

---

# Limitations

VoiceLab is a focused hackathon/research prototype rather than a complete computational-chemistry platform.

- Molecular and point-group coverage is limited to implemented workflows.
- Complex molecular geometries may require additional normalization and symmetry handling.
- Results depend on the quality and validity of the molecular geometry supplied to the pipeline.
- The current implementation focuses on molecular symmetry and related representations rather than broad quantum-chemistry calculations.
- PubChem-backed workflows depend on external molecular-data availability.
- 3D visualization is intended for interactive inspection and does not replace scientific geometry validation.
- Voice interaction depends on external API/network availability.
- Latency can vary with external services.
- Software verification does not replace independent scientific validation for research-critical decisions.

See [`LIMITATIONS.md`](LIMITATIONS.md) for the expanded limitations and future-work notes.

---

# Hackathon Demo

### Live application

https://voicelab.aspirantveda.in/

### Source code

https://github.com/PawanKumar-Gayari/voicelab

### Suggested demo request

> **“Analyze BF₃ and tell me its point group.”**

### Expected scientific highlights

```text
D₃h
12 operations
12 / 12 PASS
Γ(x,y,z) = E′ + A₂″
Research Replay
```

---

# Repository Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — detailed system and scientific architecture
- [`DEMO.md`](DEMO.md) — judge-ready demo script
- [`LIMITATIONS.md`](LIMITATIONS.md) — current limitations and future work
- [`BF3_COPILOT_DEMO.md`](BF3_COPILOT_DEMO.md) — BF₃ demonstration material
- [`README_WINDOWS_SAFE.md`](README_WINDOWS_SAFE.md) — Windows development guidance

---

# One-Line Pitch

> **VoiceLab is an AI scientific copilot that lets researchers speak a molecular-symmetry problem and receive a computed, verified, and auditable scientific result.**

---

## Built for the AssemblyAI Voice Agent Hackathon

**Voice + AI + Molecular Data + 3D Visualization + Deterministic Science + Verification**
