"""
Character calculation for molecular symmetry representations.

Core definition:

    χ(g) = Tr[D(g)]

where:
    D(g) = representation matrix of operation g
    χ(g) = character of operation g

This module is molecule-independent.
It does not determine symmetry operations and does not contain
BF3-specific geometry.
"""

from __future__ import annotations

from typing import Any

import numpy as np


CHARACTER_TOLERANCE = 1e-10


def _clean_number(value: float) -> float | int:
    """
    Convert numerical noise close to zero or an integer into a clean value.

    Examples:
        1.0000000000000002 -> 1
        -0.0000000000000001 -> 0
        -1.9999999999999998 -> -2
    """
    value = float(value)

    if abs(value) <= CHARACTER_TOLERANCE:
        return 0

    rounded = round(value)

    if abs(value - rounded) <= CHARACTER_TOLERANCE:
        return int(rounded)

    return value


def calculate_character(
    representation_matrix: list[list[float]],
) -> float | int:
    """
    Calculate the character of a representation matrix.

    Definition:

        χ(g) = Tr[D(g)]

    Parameters
    ----------
    representation_matrix:
        Square representation matrix D(g).

    Returns
    -------
    float | int
        Character χ(g).
    """
    matrix = np.asarray(representation_matrix, dtype=float)

    if matrix.ndim != 2:
        raise ValueError(
            "representation_matrix must be a two-dimensional matrix."
        )

    rows, columns = matrix.shape

    if rows != columns:
        raise ValueError(
            "representation_matrix must be a square matrix."
        )

    if not np.all(np.isfinite(matrix)):
        raise ValueError(
            "representation_matrix contains NaN or Inf."
        )

    character = np.trace(matrix)

    return _clean_number(float(character))


def calculate_characters(
    representation_matrices: dict[str, list[list[float]]],
) -> dict[str, float | int]:
    """
    Calculate characters for multiple symmetry operations.

    Parameters
    ----------
    representation_matrices:
        Dictionary mapping operation IDs to representation matrices.

    Returns
    -------
    dict
        Mapping:

            operation_id -> χ(g)
    """
    if not isinstance(representation_matrices, dict):
        raise ValueError(
            "representation_matrices must be a dictionary."
        )

    characters: dict[str, float | int] = {}

    for operation_id, matrix in representation_matrices.items():
        characters[operation_id] = calculate_character(matrix)

    return characters


def calculate_character_with_details(
    operation_id: str,
    representation_matrix: list[list[float]],
) -> dict[str, Any]:
    """
    Calculate one character and return the calculation details.

    This is useful for the voice agent and final research report because
    the result explicitly shows:

        D(g)
        χ(g) = Tr[D(g)]
    """
    matrix = np.asarray(representation_matrix, dtype=float)

    if matrix.ndim != 2:
        raise ValueError(
            "representation_matrix must be a two-dimensional matrix."
        )

    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError(
            "representation_matrix must be a square matrix."
        )

    if not np.all(np.isfinite(matrix)):
        raise ValueError(
            "representation_matrix contains NaN or Inf."
        )

    trace = float(np.trace(matrix))
    character = _clean_number(trace)

    return {
        "operation_id": operation_id,
        "representation_matrix": matrix.tolist(),
        "trace": character,
        "character": character,
        "formula": "χ(g) = Tr[D(g)]",
    }


def calculate_characters_with_details(
    representation_matrices: dict[str, list[list[float]]],
) -> dict[str, dict[str, Any]]:
    """
    Calculate characters and retain the complete trace calculation
    for every operation.
    """
    if not isinstance(representation_matrices, dict):
        raise ValueError(
            "representation_matrices must be a dictionary."
        )

    results: dict[str, dict[str, Any]] = {}

    for operation_id, matrix in representation_matrices.items():
        results[operation_id] = calculate_character_with_details(
            operation_id=operation_id,
            representation_matrix=matrix,
        )

    return results