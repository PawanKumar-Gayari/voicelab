"""Registry-driven Cartesian representation calculation.

For every operation:
    r' = M(g) r
and the selected Cartesian basis obtains D(g) from the same universal M(g).

Current MVP basis: x, y, z.
Characters are always calculated as chi(g) = Tr[D(g)].
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.science.characters import calculate_characters
from app.science.molecule_registry import get_molecule
from app.science.transformations import build_transformation_matrix


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "tool": "representation",
        "data": data,
        "error": None,
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "tool": "representation",
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _normalize_basis(basis: list[str]) -> list[str]:
    if not isinstance(basis, list) or not basis:
        raise ValueError("basis must be a non-empty list.")

    normalized = [str(item).strip().lower() for item in basis]

    if len(set(normalized)) != len(normalized):
        raise ValueError("basis functions must be unique.")

    unsupported = [item for item in normalized if item not in {"x", "y", "z"}]
    if unsupported:
        raise ValueError(
            "The current Cartesian MVP supports only x, y, and z."
        )

    return normalized


def _select_cartesian_basis(
    matrix: np.ndarray,
    basis: list[str],
) -> np.ndarray:
    index = {"x": 0, "y": 1, "z": 2}
    selected = [index[item] for item in basis]
    return matrix[np.ix_(selected, selected)]


def calculate_representation(
    molecule: str,
    basis: list[str],
    operations: list[dict],
) -> dict[str, Any]:
    """Calculate M(g), D(g), and chi(g) for a registered molecule."""
    if not isinstance(molecule, str) or not molecule.strip():
        return _failure(
            "INVALID_MOLECULE",
            "molecule must be a non-empty string.",
        )

    try:
        definition = get_molecule(molecule)
    except KeyError as exc:
        return _failure("MOLECULE_NOT_REGISTERED", str(exc))
    except Exception as exc:
        return _failure("REGISTRY_ERROR", str(exc))

    try:
        normalized_basis = _normalize_basis(basis)
    except ValueError as exc:
        return _failure("INVALID_BASIS", str(exc))

    if not isinstance(operations, list) or not operations:
        return _failure(
            "INVALID_OPERATIONS",
            "operations must be a non-empty list.",
        )

    cartesian_matrices: dict[str, list[list[float]]] = {}
    representation_matrices: dict[str, list[list[float]]] = {}

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            return _failure(
                "INVALID_OPERATION",
                f"Operation at index {index} must be a dictionary.",
            )

        operation_id = str(operation.get("id", "")).strip()
        if not operation_id:
            return _failure(
                "INVALID_OPERATION_ID",
                f"Operation at index {index} has no valid id.",
            )

        # Reconstruct M(g) from the exact operation schema. Do not trust a
        # supplied matrix for the scientific calculation.
        result = build_transformation_matrix(operation)
        if not result["success"]:
            return _failure(
                "INVALID_OPERATION",
                (
                    f"Could not build M(g) for {operation_id}: "
                    f"{result['error']['message']}"
                ),
            )

        matrix = np.asarray(result["matrix"], dtype=float)
        representation_matrix = _select_cartesian_basis(
            matrix,
            normalized_basis,
        )

        cartesian_matrices[operation_id] = matrix.tolist()
        representation_matrices[operation_id] = (
            representation_matrix.tolist()
        )

    # calculate_characters() is intentionally molecule-independent and
    # returns the character dictionary directly.
    characters = calculate_characters(representation_matrices)

    return _success(
        {
            "molecule": definition.molecule_id,
            "point_group": definition.point_group,
            "basis": normalized_basis,
            "cartesian_matrices": cartesian_matrices,
            "representation_matrices": representation_matrices,
            "characters": characters,
        }
    )
