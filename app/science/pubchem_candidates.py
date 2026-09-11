"""
Geometry-derived candidate symmetry operations.

Important boundary:
- generates only mathematically plausible candidates from a coordinate set;
- does not assign a point group;
- every candidate must be passed to VoiceLab's existing
  `geometry_symmetry.check_operation` before being accepted.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np


def _normalize(v: np.ndarray) -> np.ndarray | None:
    norm = float(np.linalg.norm(v))
    if norm <= 1e-10:
        return None
    return v / norm


def _unique_axes(axes: list[np.ndarray], tol: float = 1e-7) -> list[np.ndarray]:
    result = []
    for axis in axes:
        axis = _normalize(axis)
        if axis is None:
            continue
        if any(
            min(
                float(np.linalg.norm(axis - other)),
                float(np.linalg.norm(axis + other)),
            ) <= tol
            for other in result
        ):
            continue
        result.append(axis)
    return result


def _rotation_matrix(axis: np.ndarray, angle_deg: float) -> np.ndarray:
    axis = _normalize(axis)
    if axis is None:
        raise ValueError("Axis cannot be zero.")
    x, y, z = axis
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    C = 1.0 - c
    return np.array([
        [c+x*x*C, x*y*C-z*s, x*z*C+y*s],
        [y*x*C+z*s, c+y*y*C, y*z*C-x*s],
        [z*x*C-y*s, z*y*C+x*s, c+z*z*C],
    ], dtype=float)


def _reflection_matrix(normal: np.ndarray) -> np.ndarray:
    normal = _normalize(normal)
    if normal is None:
        raise ValueError("Plane normal cannot be zero.")
    return np.eye(3) - 2.0 * np.outer(normal, normal)


def _inversion_matrix() -> np.ndarray:
    return -np.eye(3)


def generate_candidates(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Generate a bounded, geometry-derived candidate set.

    The candidate list is intentionally conservative. It covers:
    E, inversion, principal axis candidates from atom vectors, rotations
    (multiples of 90/120/180 degrees), and planes derived from atom vectors.

    Acceptance is NOT performed here.
    """
    coords = np.asarray([a["coord"] for a in atoms], dtype=float)
    axes: list[np.ndarray] = []

    for vector in coords:
        n = _normalize(vector)
        if n is not None:
            axes.append(n)

    for a, b in itertools.combinations(coords, 2):
        cross = np.cross(a, b)
        n = _normalize(cross)
        if n is not None:
            axes.append(n)

    axes = _unique_axes(axes)

    candidates: list[dict[str, Any]] = [
        {"id": "E", "type": "identity"},
        {"id": "i", "type": "inversion"},
    ]

    for index, axis in enumerate(axes):
        for angle in (180.0, 120.0, 90.0, 60.0):
            candidates.append({
                "id": f"R{index}_{int(angle)}",
                "type": "rotation",
                "axis": axis.tolist(),
                "angle_deg": angle,
            })
        candidates.append({
            "id": f"M{index}",
            "type": "reflection",
            "plane_normal": axis.tolist(),
        })

    return candidates


def build_verified_candidates(
    atoms: list[dict[str, Any]],
    check_operation,
) -> list[dict[str, Any]]:
    """Return only candidates accepted by the existing deterministic matcher."""
    verified = []
    for operation in generate_candidates(atoms):
        result = check_operation(atoms, operation)
        if result.get("is_symmetry"):
            verified.append(operation)
    return verified
