"""
Phase-3 adapter for the existing VoiceLab science pipeline.

It intentionally does not replace app.tools.symmetry, representation, reduction,
or verification. It prepares external geometry for the existing deterministic
engines and returns a structured hand-off object.
"""

from __future__ import annotations

from typing import Any

from app.science.geometry_symmetry import check_operation
from app.science.pubchem_candidates import generate_candidates
from app.science.pubchem_operation_classifier import classify_matrix


def verify_and_classify_candidates(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Verify candidates using the existing matcher, then classify their matrices."""
    verified = []

    for candidate in generate_candidates(atoms):
        result = check_operation(atoms, candidate)
        if not result.get("is_symmetry"):
            continue

        matrix = result.get("matrix")
        classification = classify_matrix(matrix)

        item = dict(candidate)
        item["matrix"] = matrix
        item["verified"] = True
        item["classification"] = classification
        verified.append(item)

    return verified


def prepare_external_geometry(atoms: list[dict[str, Any]]) -> dict[str, Any]:
    """Create the deterministic hand-off consumed by the next registry phase."""
    operations = verify_and_classify_candidates(atoms)

    return {
        "success": True,
        "source": "pubchem",
        "atoms": atoms,
        "operations": operations,
        "operation_count": len(operations),
    }
