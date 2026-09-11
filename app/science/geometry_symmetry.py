"""Generic coordinate-based symmetry testing.

No molecule-specific logic lives here.  A transformation is a symmetry
operation iff transformed atoms can be bijectively matched to original atoms
of the same element within a numerical tolerance.
"""
from __future__ import annotations

from typing import Any
import numpy as np

from app.science.transformations import build_transformation_matrix

DEFAULT_TOLERANCE = 1e-7


def _atoms_from_coordinates(coordinates: Any) -> list[dict[str, Any]]:
    if isinstance(coordinates, dict):
        atoms = []
        for label, value in coordinates.items():
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                raise ValueError(f"Coordinate for {label!r} must contain 3 values.")
            element = ''.join(ch for ch in str(label) if ch.isalpha()) or str(label)
            atoms.append({"label": str(label), "element": element, "coord": [float(x) for x in value]})
        return atoms
    if isinstance(coordinates, list):
        atoms = []
        for i, atom in enumerate(coordinates):
            if isinstance(atom, dict):
                element = str(atom.get("element") or atom.get("symbol") or "X")
                coord = atom.get("coord") or [atom.get("x"), atom.get("y"), atom.get("z")]
            else:
                element, *coord = atom
            if len(coord) != 3:
                raise ValueError(f"Atom {i} must contain a 3D coordinate.")
            atoms.append({"label": str(atom.get("id", i)) if isinstance(atom, dict) else str(i), "element": element, "coord": [float(x) for x in coord]})
        return atoms
    raise ValueError("coordinates must be a mapping or list of atoms.")


def check_operation(coordinates: Any, operation: dict[str, Any], tolerance: float = DEFAULT_TOLERANCE) -> dict[str, Any]:
    """Build M, transform all coordinates, and perform element-preserving matching."""
    atoms = _atoms_from_coordinates(coordinates)
    built = build_transformation_matrix(operation)
    if not built.get("success"):
        return {"success": False, "is_symmetry": False, "operation": operation, "matrix": None, "transformed_coordinates": [], "mapping": [], "error": built.get("error")}

    matrix = np.asarray(built["matrix"], dtype=float)
    original = np.asarray([a["coord"] for a in atoms], dtype=float)
    transformed = (matrix @ original.T).T
    # Find a globally valid bijection between transformed atoms and
    # original atoms of the same element.  Greedy nearest-neighbour
    # matching is incorrect for symmetry-equivalent atoms (for example
    # the four Cl atoms in CCl4), because an early atom can consume the
    # nearest target needed by a later atom.
    mapping_indices: dict[int, int] = {}

    def _assign_group(source_indices: list[int], target_indices: list[int]) -> bool:
        if len(source_indices) != len(target_indices):
            return False

        if not source_indices:
            return True

        distances = np.asarray(
            [
                [
                    float(
                        np.linalg.norm(
                            transformed[source_i] - original[target_j]
                        )
                    )
                    for target_j in target_indices
                ]
                for source_i in source_indices
            ],
            dtype=float,
        )

        # For the small external molecules handled by this symmetry
        # verifier, exhaustive assignment gives an exact bijective
        # criterion without introducing a dependency on a solver package.
        import itertools

        best = None
        best_cost = float("inf")

        for permutation in itertools.permutations(range(len(target_indices))):
            selected = [
                distances[row, column]
                for row, column in enumerate(permutation)
            ]

            if any(distance > tolerance for distance in selected):
                continue

            cost = float(sum(distance * distance for distance in selected))

            if cost < best_cost:
                best_cost = cost
                best = permutation

        if best is None:
            return False

        for row, column in enumerate(best):
            mapping_indices[source_indices[row]] = target_indices[column]

        return True

    element_groups: dict[str, list[int]] = {}

    for index, atom in enumerate(atoms):
        element_groups.setdefault(
            atom["element"].upper(),
            [],
        ).append(index)

    for element, indices in element_groups.items():
        if not _assign_group(indices, indices):
            break

    mapping: list[dict[str, Any]] = []

    for i, atom in enumerate(atoms):
        j = mapping_indices.get(i)

        if j is None:
            mapping.append({
                "from": atom["label"],
                "element": atom["element"],
                "match": None,
                "distance": None,
            })
            continue

        distance = float(
            np.linalg.norm(
                transformed[i] - original[j]
            )
        )

        mapping.append({
            "from": atom["label"],
            "element": atom["element"],
            "match": atoms[j]["label"],
            "distance": distance,
        })

    is_symmetry = (
        len(mapping_indices) == len(atoms)
        and len(set(mapping_indices.values())) == len(atoms)
        and all(
            item["match"] is not None
            for item in mapping
        )
    )
    return {
        "success": True,
        "is_symmetry": is_symmetry,
        "operation": operation,
        "matrix": matrix.tolist(),
        "transformed_coordinates": {a["label"]: transformed[i].tolist() for i, a in enumerate(atoms)},
        "mapping": mapping,
        "tolerance": tolerance,
        "error": None,
    }
