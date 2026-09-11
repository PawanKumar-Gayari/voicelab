"""
Geometry normalization for externally sourced molecular coordinates.

This intentionally performs only coordinate hygiene. It never assigns a
point group and never treats an external point-group label as truth.
"""

from __future__ import annotations

import math
from typing import Iterable


def normalize_atoms(atoms: Iterable[dict]) -> list[dict]:
    atoms = list(atoms)
    if not atoms:
        raise ValueError("Molecule must contain at least one atom.")

    cleaned = []
    for index, atom in enumerate(atoms, start=1):
        element = str(atom.get("element", "")).strip()
        coord = atom.get("coord")
        if not element or not isinstance(coord, (list, tuple)) or len(coord) != 3:
            raise ValueError(f"Invalid atom record at index {index}.")
        values = [float(v) for v in coord]
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"Non-finite coordinate at index {index}.")
        cleaned.append({
            "label": str(atom.get("label") or f"{element}{index}"),
            "element": element,
            "coord": values,
        })

    # Keep the source geometry unchanged for scientific reproducibility.
    # Centering/orientation must be an explicit later scientific operation,
    # because an arbitrary rotation can invalidate a fixed Cartesian registry.
    return cleaned
