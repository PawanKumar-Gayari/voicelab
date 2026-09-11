"""
BF3 scientific orchestration tool for VoiceLab.

This module is a thin bridge between the existing VoiceLab tools and the
molecule-independent D3h scientific data.

Flow:
    bf3.py
        -> transformation matrices
    representation.py
        -> D(g), chi(g)
    d3h.py
        -> D3h classes, character table, irreps, reduction
    verification.py
        -> independent verification

The existing voice/tool flow is not changed by this module. It is designed
to be callable directly by future orchestration code while preserving the
existing symmetry, representation, and verification tools.
"""

from __future__ import annotations

from typing import Any

from app.science.bf3 import get_bf3_symmetry_data
from app.science.d3h import (
    get_d3h_character_table,
    get_d3h_classes,
    reduce_representation,
)
from app.tools.representation import calculate_representation
from app.tools.verification import verify_representation


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "tool": "bf3_analysis",
        "data": data,
        "error": None,
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "tool": "bf3_analysis",
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def analyze_bf3(
    basis: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run the complete deterministic BF3 symmetry pipeline.

    Default basis:
        x, y, z

    Returns:
        symmetry data
        representation data
        D3h character table
        reduced representation
        independent verification result
    """
    if basis is None:
        basis = ["x", "y", "z"]

    if not isinstance(basis, list) or not all(
        isinstance(item, str) for item in basis
    ):
        return _failure(
            "INVALID_BASIS",
            "basis must be a list of strings.",
        )

    if not basis:
        return _failure(
            "INVALID_BASIS",
            "basis must contain at least one basis function.",
        )

    # 1. Molecule-specific BF3 geometry and D3h operations.
    try:
        symmetry_data = get_bf3_symmetry_data()
    except Exception as exc:
        return _failure(
            "BF3_SYMMETRY_FAILED",
            f"Failed to obtain BF3 symmetry data: {exc}",
        )

    molecule_data = symmetry_data.get("molecule", {})
    operations = symmetry_data.get("operations", [])

    if not molecule_data or not operations:
        return _failure(
            "INVALID_BF3_DATA",
            "BF3 symmetry data is incomplete.",
        )

    # 2. Existing representation tool computes actual D(g) and chi(g).
    representation_result = calculate_representation(
        molecule="BF3",
        basis=basis,
        operations=operations,
    )

    if not representation_result.get("success"):
        return _failure(
            "REPRESENTATION_FAILED",
            str(representation_result.get("error")),
        )

    representation = representation_result.get("data", {})

    representation_matrices = representation.get(
        "representation_matrices",
        {},
    )
    characters = representation.get("characters", {})

    if not representation_matrices or not characters:
        return _failure(
            "INCOMPLETE_REPRESENTATION",
            "Representation matrices or characters are missing.",
        )

    # 3. D3h supplies the group classes/irreps and performs reduction.
    d3h_table = get_d3h_character_table()
    d3h_classes = get_d3h_classes()

    # Map operation IDs to the six D3h classes. The BF3 operation definitions
    # use explicit IDs, while d3h.py works at conjugacy-class level.
    class_characters: dict[str, float] = {}
    operation_to_class: dict[str, str] = {}

    for operation in operations:
        operation_id = str(operation.get("id", ""))
        symbol = str(operation.get("symbol", operation_id))

        if operation_id == "E":
            class_symbol = "E"
        elif operation_id in {"C3_1", "C3_2"}:
            class_symbol = "2C3"
        elif operation_id in {"C2p_1", "C2p_2", "C2p_3"}:
            class_symbol = "3C2'"
        elif operation_id == "sigma_h":
            class_symbol = "sigma_h"
        elif operation_id in {"S3_1", "S3_2"}:
            class_symbol = "2S3"
        elif operation_id in {"sigma_v_1", "sigma_v_2", "sigma_v_3"}:
            class_symbol = "3sigma_v"
        else:
            return _failure(
                "UNKNOWN_D3H_OPERATION",
                f"Operation {operation_id or symbol!r} is not mapped to a D3h class.",
            )

        operation_to_class[operation_id] = class_symbol
        class_characters.setdefault(
            class_symbol,
            float(characters[operation_id]),
        )

    required_classes = [
        item["symbol"]
        for item in d3h_classes
    ]

    if any(class_symbol not in class_characters for class_symbol in required_classes):
        return _failure(
            "INCOMPLETE_D3H_CLASSES",
            "The BF3 representation does not contain all six D3h classes.",
        )

    reducible_characters = [
        class_characters[class_symbol]
        for class_symbol in required_classes
    ]

    try:
        reduction = reduce_representation(reducible_characters)
    except Exception as exc:
        return _failure(
            "REDUCTION_FAILED",
            f"Failed to reduce the BF3 representation: {exc}",
        )

    # 4. Existing independent verification tool remains the final gate.
    verification_result = verify_representation(
        molecule="BF3",
        operations=operations,
        representation_matrices=representation_matrices,
        characters=characters,
    )

    if not verification_result.get("success"):
        return _failure(
            "VERIFICATION_FAILED",
            str(verification_result.get("error")),
        )

    verification = verification_result.get("data", {})

    return _success(
        {
            "molecule": molecule_data,
            "point_group": molecule_data.get("point_group", "D3h"),
            "operations": operations,
            "basis": basis,
            "representation": representation,
            "d3h": {
                "classes": d3h_classes,
                "character_table": d3h_table,
                "operation_to_class": operation_to_class,
                "reducible_characters": reducible_characters,
                "reduction": reduction,
            },
            "verification": verification,
        }
    )


# Explicit alias for callers that prefer the tool-style name.
def analyze_bf3_symmetry(
    basis: list[str] | None = None,
) -> dict[str, Any]:
    """Tool-style alias for the complete BF3 analysis."""
    return analyze_bf3(basis=basis)
