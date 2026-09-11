"""
Universal Cartesian symmetry transformation engine.

Convention:
    r' = M @ r

Supported operations:
    - identity
    - rotation
    - reflection
    - inversion
    - improper_rotation

This module is molecule-independent and contains no BF3-specific logic.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


MATRIX_TOLERANCE = 1e-10


def _error(code: str, message: str) -> dict[str, Any]:
    """Create a standardized transformation error response."""
    return {
        "success": False,
        "operation": None,
        "matrix": None,
        "metadata": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _normalize_vector(
    vector: list[float],
    name: str,
) -> np.ndarray:
    """Validate and normalize a 3D vector."""
    if not isinstance(vector, (list, tuple)):
        raise ValueError(f"{name} must be a 3D vector.")

    if len(vector) != 3:
        raise ValueError(f"{name} must contain exactly 3 components.")

    try:
        values = np.asarray(vector, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric values.") from exc

    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must contain only finite values.")

    norm = np.linalg.norm(values)

    if norm <= MATRIX_TOLERANCE:
        raise ValueError(f"{name} must be a non-zero 3D vector.")

    return values / norm


def _validate_angle(angle_deg: Any) -> float:
    """Validate and convert an angle to float degrees."""
    try:
        angle = float(angle_deg)
    except (TypeError, ValueError) as exc:
        raise ValueError("angle_deg must be a finite number.") from exc

    if not math.isfinite(angle):
        raise ValueError("angle_deg must be a finite number.")

    return angle


def _build_rotation_matrix(
    axis: list[float],
    angle_deg: float,
) -> np.ndarray:
    """
    Build a rotation matrix using Rodrigues' rotation formula.

    Positive angles follow the right-hand rule in a fixed Cartesian frame.
    """
    n = _normalize_vector(axis, "axis")
    theta = math.radians(_validate_angle(angle_deg))

    nx, ny, nz = n

    # Cross-product matrix for the normalized axis.
    k = np.array(
        [
            [0.0, -nz, ny],
            [nz, 0.0, -nx],
            [-ny, nx, 0.0],
        ],
        dtype=float,
    )

    identity = np.eye(3, dtype=float)

    # Rodrigues formula:
    # R = I cos(theta) + (1-cos(theta)) nn^T + sin(theta) K
    rotation = (
        identity * math.cos(theta)
        + (1.0 - math.cos(theta)) * np.outer(n, n)
        + math.sin(theta) * k
    )

    return rotation


def _build_reflection_matrix(
    plane_normal: list[float],
) -> np.ndarray:
    """
    Build a reflection matrix.

    The reflection plane passes through the origin and is defined by
    its normal vector n:

        M = I - 2 n_hat n_hat^T
    """
    n = _normalize_vector(plane_normal, "plane_normal")

    identity = np.eye(3, dtype=float)

    reflection = identity - 2.0 * np.outer(n, n)

    return reflection


def _build_improper_rotation_matrix(
    axis: list[float],
    angle_deg: float,
) -> np.ndarray:
    """
    Build an improper-rotation matrix.

    Definition used by this project:

        S_n = sigma_h C_n

    where sigma_h is reflection through the plane perpendicular
    to the rotation axis.

    The rotation is applied first, followed by the reflection.
    Therefore:

        M = sigma_h @ C_n
    """
    normalized_axis = _normalize_vector(axis, "axis")

    rotation = _build_rotation_matrix(
        axis=axis,
        angle_deg=angle_deg,
    )

    reflection = _build_reflection_matrix(
        plane_normal=normalized_axis.tolist(),
    )

    return reflection @ rotation


def _matrix_metadata(matrix: np.ndarray) -> dict[str, Any]:
    """Calculate standard metadata for a 3x3 transformation matrix."""
    determinant = float(np.linalg.det(matrix))

    orthogonal = bool(
        np.allclose(
            matrix.T @ matrix,
            np.eye(3),
            atol=MATRIX_TOLERANCE,
            rtol=MATRIX_TOLERANCE,
        )
    )

    return {
        "dimension": 3,
        "determinant": determinant,
        "orthogonal": orthogonal,
    }


def build_transformation_matrix(operation: dict) -> dict[str, Any]:
    """
    Build a universal Cartesian transformation matrix.

    Parameters
    ----------
    operation:
        Dictionary describing the symmetry operation.

    Returns
    -------
    dict
        Standardized success/failure response.
    """
    if not isinstance(operation, dict):
        return _error(
            "INVALID_OPERATION",
            "operation must be a dictionary.",
        )

    operation_type = operation.get("type")

    if not isinstance(operation_type, str):
        return _error(
            "INVALID_OPERATION_TYPE",
            "operation type must be a string.",
        )

    operation_type = operation_type.strip().lower()

    try:
        if operation_type == "identity":
            matrix = np.eye(3, dtype=float)

        elif operation_type == "rotation":
            if "axis" not in operation:
                return _error(
                    "MISSING_AXIS",
                    "Rotation operation requires an axis.",
                )

            if "angle_deg" not in operation:
                return _error(
                    "MISSING_ANGLE",
                    "Rotation operation requires angle_deg.",
                )

            matrix = _build_rotation_matrix(
                axis=operation["axis"],
                angle_deg=operation["angle_deg"],
            )

        elif operation_type == "reflection":
            if "plane_normal" not in operation:
                return _error(
                    "MISSING_PLANE_NORMAL",
                    "Reflection operation requires plane_normal.",
                )

            matrix = _build_reflection_matrix(
                plane_normal=operation["plane_normal"],
            )

        elif operation_type == "inversion":
            matrix = -np.eye(3, dtype=float)

        elif operation_type == "improper_rotation":
            if "axis" not in operation:
                return _error(
                    "MISSING_AXIS",
                    "Improper rotation operation requires an axis.",
                )

            if "angle_deg" not in operation:
                return _error(
                    "MISSING_ANGLE",
                    "Improper rotation operation requires angle_deg.",
                )

            matrix = _build_improper_rotation_matrix(
                axis=operation["axis"],
                angle_deg=operation["angle_deg"],
            )

        else:
            return _error(
                "INVALID_OPERATION_TYPE",
                (
                    f"Unsupported operation type: "
                    f"{operation_type!r}. Supported types are: "
                    "identity, rotation, reflection, inversion, "
                    "improper_rotation."
                ),
            )

    except ValueError as exc:
        message = str(exc)

        if "axis" in message.lower():
            code = "INVALID_AXIS"
        elif "plane_normal" in message.lower():
            code = "INVALID_PLANE_NORMAL"
        elif "angle" in message.lower():
            code = "INVALID_ANGLE"
        else:
            code = "INVALID_OPERATION"

        return _error(code, message)

    matrix = np.asarray(matrix, dtype=float)

    validation = validate_transformation_matrix(
        matrix.tolist(),
        operation_type,
    )

    if not validation["success"]:
        return {
            "success": False,
            "operation": None,
            "matrix": None,
            "metadata": None,
            "error": validation["error"],
        }

    metadata = _matrix_metadata(matrix)

    return {
        "success": True,
        "operation": {
            **operation,
            "type": operation_type,
        },
        "matrix": matrix.tolist(),
        "metadata": metadata,
        "error": None,
    }


def validate_transformation_matrix(
    matrix: list[list[float]],
    operation_type: str,
) -> dict[str, Any]:
    """
    Validate a 3x3 Cartesian transformation matrix.

    Checks:
        1. Shape is 3x3.
        2. All values are finite.
        3. Matrix is orthogonal.
        4. Determinant matches the operation type.
    """
    if not isinstance(matrix, (list, tuple)):
        return {
            "success": False,
            "error": {
                "code": "INVALID_MATRIX",
                "message": "Matrix must be a 3x3 array.",
            },
        }

    try:
        array = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError):
        return {
            "success": False,
            "error": {
                "code": "INVALID_MATRIX",
                "message": "Matrix must contain numeric values.",
            },
        }

    if array.shape != (3, 3):
        return {
            "success": False,
            "error": {
                "code": "INVALID_MATRIX_SHAPE",
                "message": "Transformation matrix must have shape 3x3.",
            },
        }

    if not np.all(np.isfinite(array)):
        return {
            "success": False,
            "error": {
                "code": "NONFINITE_MATRIX",
                "message": "Transformation matrix contains NaN or Inf.",
            },
        }

    orthogonal = np.allclose(
        array.T @ array,
        np.eye(3),
        atol=MATRIX_TOLERANCE,
        rtol=MATRIX_TOLERANCE,
    )

    if not orthogonal:
        return {
            "success": False,
            "error": {
                "code": "NON_ORTHOGONAL_MATRIX",
                "message": "Transformation matrix must be orthogonal.",
            },
        }

    operation_type = str(operation_type).strip().lower()

    determinant = float(np.linalg.det(array))

    if operation_type in {"identity", "rotation"}:
        expected_determinant = 1.0

    elif operation_type in {
        "reflection",
        "inversion",
        "improper_rotation",
    }:
        expected_determinant = -1.0

    else:
        return {
            "success": False,
            "error": {
                "code": "INVALID_OPERATION_TYPE",
                "message": (
                    f"Unsupported operation type: {operation_type!r}."
                ),
            },
        }

    if not math.isclose(
        determinant,
        expected_determinant,
        abs_tol=MATRIX_TOLERANCE,
        rel_tol=MATRIX_TOLERANCE,
    ):
        return {
            "success": False,
            "error": {
                "code": "INVALID_DETERMINANT",
                "message": (
                    f"Expected determinant {expected_determinant:+.1f} "
                    f"for {operation_type}, but got {determinant:+.12f}."
                ),
            },
        }

    return {
        "success": True,
        "error": None,
        "metadata": {
            "dimension": 3,
            "determinant": determinant,
            "orthogonal": True,
        },
    }


def compose_transformations(
    first: list[list[float]],
    second: list[list[float]],
) -> list[list[float]]:
    """
    Compose two Cartesian transformations.

    If `first` is applied first and `second` is applied second:

        r1 = first @ r
        r2 = second @ r1

    therefore:

        r2 = (second @ first) @ r

    Hence the returned matrix is:

        second @ first
    """
    first_array = np.asarray(first, dtype=float)
    second_array = np.asarray(second, dtype=float)

    if first_array.shape != (3, 3):
        raise ValueError("first transformation must be a 3x3 matrix.")

    if second_array.shape != (3, 3):
        raise ValueError("second transformation must be a 3x3 matrix.")

    if not np.all(np.isfinite(first_array)):
        raise ValueError("first transformation contains NaN or Inf.")

    if not np.all(np.isfinite(second_array)):
        raise ValueError("second transformation contains NaN or Inf.")

    composed = second_array @ first_array

    return composed.tolist()


def apply_transformation(
    matrix: list[list[float]],
    vector: list[float],
) -> list[float]:
    """
    Apply a Cartesian transformation to a 3D vector.

    Convention:

        r' = M @ r
    """
    matrix_array = np.asarray(matrix, dtype=float)
    vector_array = np.asarray(vector, dtype=float)

    if matrix_array.shape != (3, 3):
        raise ValueError("matrix must be a 3x3 matrix.")

    if vector_array.shape != (3,):
        raise ValueError("vector must contain exactly 3 components.")

    if not np.all(np.isfinite(matrix_array)):
        raise ValueError("matrix contains NaN or Inf.")

    if not np.all(np.isfinite(vector_array)):
        raise ValueError("vector contains NaN or Inf.")

    transformed = matrix_array @ vector_array

    return transformed.tolist()