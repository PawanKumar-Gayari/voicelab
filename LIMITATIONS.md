# VoiceLab — Current Limitations

VoiceLab is a focused hackathon/research prototype.

## Scientific Scope

- Supported molecules and point groups are limited to implemented workflows.
- It is not a general-purpose quantum-chemistry package.
- Complex geometries can require additional normalization and symmetry handling.
- Scientific output depends on the molecular geometry supplied to the pipeline.

## Voice / Infrastructure

- Voice interaction depends on AssemblyAI and real-time voice infrastructure.
- Network/API availability can affect voice sessions.
- Latency can vary with external services.

## Validation

The system includes automated tests and deterministic verification, but software verification does not replace independent scientific validation for research-critical decisions.

## Production Scope

The project demonstrates a scientific-agent workflow. It should not be interpreted as a validated replacement for established computational-chemistry software or expert review.

## Future Work

- broader molecule and point-group coverage
- more robust arbitrary-geometry handling
- richer orbital and vibrational representations
- stronger scientific provenance and export
- expanded benchmark/regression datasets
- additional offline/fallback capabilities
