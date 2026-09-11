"""Principal-axis based symmetry candidate generation for external geometries.

This module is intentionally independent of VoiceLab's molecule registry.
Coordinates are centered and an inertia/covariance frame is used to discover
candidate axes before numerical verification. It does not assign a point group.
"""

from __future__ import annotations
import itertools
import math
from typing import Any
import numpy as np

TOL = 1e-7

def _array(atoms):
    xyz = []
    for atom in atoms:
        xyz.append(np.asarray(atom["coords"], dtype=float))
    if not xyz:
        raise ValueError("No atoms supplied.")
    return np.asarray(xyz, dtype=float)

def center_geometry(atoms):
    xyz = _array(atoms)
    center = xyz.mean(axis=0)
    centered = xyz - center
    return [dict(atom, coords=centered[i].tolist()) for i, atom in enumerate(atoms)], center.tolist()

def _canonical_axis(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n <= TOL:
        return None
    v = v / n
    for x in v:
        if abs(x) > TOL:
            if x < 0: v = -v
            break
    return v

def principal_axes(atoms):
    centered, center = center_geometry(atoms)
    xyz = _array(centered)
    cov = xyz.T @ xyz
    values, vectors = np.linalg.eigh(cov)
    axes = []
    for i in range(3):
        axis = _canonical_axis(vectors[:, i])
        if axis is not None:
            axes.append(axis)
    return centered, center, axes, values.tolist()

def candidate_axes(atoms):
    centered, center, axes, eigenvalues = principal_axes(atoms)
    xyz = _array(centered)
    found = {tuple(np.round(a, 10)) for a in axes}

    # Add normalized atom directions and pairwise cross products. This catches
    # degenerate principal moments where an eigensolver frame is not unique.
    for v in xyz:
        a = _canonical_axis(v)
        if a is not None: found.add(tuple(np.round(a, 10)))
    for a, b in itertools.combinations(xyz, 2):
        c = np.cross(a, b)
        c = _canonical_axis(c)
        if c is not None: found.add(tuple(np.round(c, 10)))

    ordered = [np.asarray(v, dtype=float) for v in sorted(found)]
    return centered, center, ordered, eigenvalues

def rotation_matrix(axis, angle_deg):
    axis = _canonical_axis(axis)
    if axis is None: raise ValueError("Invalid rotation axis.")
    t = math.radians(angle_deg)
    x, y, z = axis
    c, s = math.cos(t), math.sin(t)
    C = 1-c
    return np.array([
        [c+x*x*C, x*y*C-z*s, x*z*C+y*s],
        [y*x*C+z*s, c+y*y*C, y*z*C-x*s],
        [z*x*C-y*s, z*y*C+x*s, c+z*z*C],
    ])

def reflection_matrix(normal):
    n = _canonical_axis(normal)
    if n is None: raise ValueError("Invalid plane normal.")
    return np.eye(3) - 2*np.outer(n, n)

def improper_rotation_matrix(axis, angle_deg):
    return reflection_matrix(axis) @ rotation_matrix(axis, angle_deg)

def generate_principal_axis_candidates(atoms):
    centered, center, axes, eigenvalues = candidate_axes(atoms)
    candidates = [{"id":"E","type":"identity"}]

    # Orders currently supported by the registry-backed point groups.
    angles = (180.0, 120.0, 90.0, 60.0)
    seen = set()
    for axis in axes:
        for angle in angles:
            m = rotation_matrix(axis, angle)
            key = tuple(np.round(m, 8).ravel())
            if key not in seen:
                seen.add(key)
                candidates.append({
                    "id": f"R_{len(candidates)}",
                    "type": "rotation",
                    "axis": axis.tolist(),
                    "angle_deg": angle,
                })
        # Reflection through plane perpendicular to this candidate axis.
        m = reflection_matrix(axis)
        key = tuple(np.round(m, 8).ravel())
        if key not in seen:
            seen.add(key)
            candidates.append({
                "id": f"M_{len(candidates)}",
                "type": "reflection",
                "plane_normal": axis.tolist(),
            })
        for angle in (90.0, 120.0, 60.0):
            m = improper_rotation_matrix(axis, angle)
            key = tuple(np.round(m, 8).ravel())
            if key not in seen:
                seen.add(key)
                candidates.append({
                    "id": f"S_{len(candidates)}",
                    "type": "improper_rotation",
                    "axis": axis.tolist(),
                    "angle_deg": angle,
                })

    candidates.append({"id":"i","type":"inversion"})
    return centered, center, eigenvalues, candidates
