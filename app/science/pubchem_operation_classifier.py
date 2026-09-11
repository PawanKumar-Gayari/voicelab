"""
Deterministic classification of Cartesian symmetry matrices.

The classifier converts an already-verified 3x3 Cartesian matrix into a
canonical operation description. It does not decide the molecule's point
group and does not use external point-group metadata.
"""

from __future__ import annotations

import math
import numpy as np


TOLERANCE = 1e-7


def _matrix(operation: dict) -> np.ndarray:
    matrix = operation.get("matrix")
    if matrix is None:
        raise ValueError("Verified operation must contain a matrix.")
    value = np.asarray(matrix, dtype=float)
    if value.shape != (3, 3):
        raise ValueError("Operation matrix must be 3x3.")
    return value


def _rotation_angle(matrix: np.ndarray) -> float:
    cosine = max(-1.0, min(1.0, (float(np.trace(matrix)) - 1.0) / 2.0))
    return math.degrees(math.acos(cosine))


def _axis_from_matrix(matrix: np.ndarray) -> list[float] | None:
    values, vectors = np.linalg.eig(matrix)
    for index, value in enumerate(values):
        if abs(float(np.imag(value))) <= TOLERANCE and abs(float(np.real(value)) - 1.0) <= TOLERANCE:
            axis = np.real(vectors[:, index]).astype(float)
            norm = float(np.linalg.norm(axis))
            if norm > TOLERANCE:
                axis /= norm
                # deterministic sign
                for component in axis:
                    if abs(component) > TOLERANCE:
                        if component < 0:
                            axis = -axis
                        break
                return axis.tolist()
    return None


def classify_matrix(matrix: list[list[float]] | np.ndarray) -> dict:
    """Classify a verified orthogonal Cartesian operation matrix."""
    m = np.asarray(matrix, dtype=float)
    if m.shape != (3, 3):
        raise ValueError("Operation matrix must be 3x3.")

    determinant = float(np.linalg.det(m))
    trace = float(np.trace(m))

    if np.allclose(m, np.eye(3), atol=TOLERANCE):
        return {"type": "identity", "symbol": "E", "order": 1}

    if np.allclose(m, -np.eye(3), atol=TOLERANCE):
        return {"type": "inversion", "symbol": "i", "order": 2}

    if abs(determinant - 1.0) <= TOLERANCE:
        angle = _rotation_angle(m)
        if abs(angle) <= TOLERANCE:
            return {"type": "identity", "symbol": "E", "order": 1}
        nearest = max(1, int(round(360.0 / angle)))
        return {
            "type": "rotation",
            "symbol": f"C{nearest}",
            "order": nearest,
            "angle_deg": angle,
            "axis": _axis_from_matrix(m),
        }

    # A proper reflection has det=-1 and trace=1.
    if abs(determinant + 1.0) <= TOLERANCE and abs(trace - 1.0) <= TOLERANCE:
        values, vectors = np.linalg.eig(m)
        normal = None
        for index, value in enumerate(values):
            if abs(float(np.imag(value))) <= TOLERANCE and abs(float(np.real(value)) + 1.0) <= TOLERANCE:
                vector = np.real(vectors[:, index]).astype(float)
                norm = float(np.linalg.norm(vector))
                if norm > TOLERANCE:
                    vector /= norm
                    normal = vector.tolist()
                    break
        return {
            "type": "reflection",
            "symbol": "sigma",
            "plane_normal": normal,
        }

    # Remaining det=-1 orthogonal matrices are improper rotations S_n.
    proper = -m
    angle = _rotation_angle(proper)
    if abs(angle) <= TOLERANCE:
        return {"type": "improper_rotation", "symbol": "S2", "order": 2}

    nearest = max(2, int(round(360.0 / angle)))
    return {
        "type": "improper_rotation",
        "symbol": f"S{nearest}",
        "order": nearest,
        "angle_deg": angle,
        "axis": _axis_from_matrix(proper),
    }
