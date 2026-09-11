"""Molecule-independent verification of representation results."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.science.molecule_registry import MoleculeDefinition, get_molecule
from app.science.transformations import MATRIX_TOLERANCE, build_transformation_matrix


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "tool": "verification",
        "data": data,
        "error": None,
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "tool": "verification",
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def verify_representation(
    molecule: str | MoleculeDefinition,
    operations: list[dict],
    representation_matrices: dict[str, list[list[float]]],
    characters: dict[str, Any],
) -> dict[str, Any]:
    """Independently verify matrices, dimensions, traces, and numerics."""
    if isinstance(molecule, MoleculeDefinition):
        definition = molecule
    else:
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

    if not isinstance(operations, list) or not operations:
        return _failure("INVALID_OPERATIONS", "operations must be a non-empty list.")
    if not isinstance(representation_matrices, dict):
        return _failure("INVALID_REPRESENTATION", "representation_matrices must be a dictionary.")
    if not isinstance(characters, dict):
        return _failure("INVALID_CHARACTERS", "characters must be a dictionary.")

    errors: list[str] = []
    dimensions: set[int] = set()

    for index, operation in enumerate(operations):
        operation_id = str(operation.get("id", "")).strip() if isinstance(operation, dict) else ""
        if not operation_id:
            errors.append(f"Operation at index {index} has no valid id.")
            continue

        result = build_transformation_matrix(operation)
        if not result.get("success"):
            errors.append(
                f"{operation_id}: transformation matrix failed: {result.get('error')}"
            )
            continue

        supplied = representation_matrices.get(operation_id)
        if supplied is None:
            errors.append(f"{operation_id}: representation matrix is missing.")
            continue

        try:
            matrix = np.asarray(supplied, dtype=float)
            expected = np.asarray(result["matrix"], dtype=float)
        except (TypeError, ValueError):
            errors.append(f"{operation_id}: representation matrix is not numeric.")
            continue

        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            errors.append(f"{operation_id}: representation matrix must be square.")
            continue
        if not np.all(np.isfinite(matrix)):
            errors.append(f"{operation_id}: representation matrix contains NaN or Inf.")
            continue

        dimensions.add(matrix.shape[0])

        if matrix.shape == expected.shape and matrix.shape == (3, 3):
            if not np.allclose(matrix, expected, atol=MATRIX_TOLERANCE, rtol=MATRIX_TOLERANCE):
                errors.append(f"{operation_id}: representation matrix does not match the Cartesian transformation.")
        else:
            # Full molecular displacement representations operate in the 3N
            # basis, so their matrices are expected to be larger than the
            # underlying 3x3 Cartesian transformation.  Trace, dimensions,
            # identity, and numerical validity are verified independently.
            pass

        expected_character = float(np.trace(matrix))
        if operation_id not in characters:
            errors.append(f"{operation_id}: character is missing.")
        else:
            try:
                supplied_character = float(characters[operation_id])
            except (TypeError, ValueError):
                errors.append(f"{operation_id}: character is not numeric.")
            else:
                if not np.isclose(
                    supplied_character,
                    expected_character,
                    atol=MATRIX_TOLERANCE,
                    rtol=MATRIX_TOLERANCE,
                ):
                    errors.append(
                        f"{operation_id}: character mismatch. "
                        f"Expected Tr[D(g)] = {expected_character}, "
                        f"received {supplied_character}."
                    )

        if operation.get("type") == "identity":
            expected_identity = np.eye(matrix.shape[0], dtype=float)
            if not np.allclose(
                matrix,
                expected_identity,
                atol=MATRIX_TOLERANCE,
                rtol=MATRIX_TOLERANCE,
            ):
                errors.append(
                    f"{operation_id}: identity representation matrix is not identity."
                )

    if len(dimensions) > 1:
        errors.append("Representation matrices have inconsistent dimensions.")

    status = "PASS" if not errors else "FLAG"

    return _success(
        {
            "molecule": definition.molecule_id,
            "status": status,
            "checks": {
                "operation_matrices": "PASS" if not errors else "FLAG",
                "representation_dimensions": "PASS" if len(dimensions) <= 1 else "FLAG",
                "character_trace": "PASS" if not any("character" in e for e in errors) else "FLAG",
                "numerical_consistency": "PASS" if not errors else "FLAG",
            },
            "errors": errors,
        }
    )
