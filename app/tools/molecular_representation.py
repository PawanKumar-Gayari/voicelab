"""Universal molecular 3N displacement representation.

This module is molecule-independent.

Pipeline:
    registered molecule
        -> universal Cartesian transformation M(g)
        -> geometric atom mapping
        -> 3N displacement representation D(g)
        -> character chi(g) = Tr[D(g)]
        -> conjugacy-class characters
        -> generic irreducible reduction

No molecule-specific coordinates, operation ids, or character tables
are hard-coded here.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.science.molecule_registry import MoleculeDefinition, get_molecule
from app.science.point_group_registry import get_point_group
from app.science.class_resolver import resolve_operation_class
from app.science.reduction import format_reduction_summary, reduce_representation
from app.science.transformations import build_transformation_matrix
from app.tools.symmetry import analyze_symmetry


DEFAULT_TOLERANCE = 1e-7


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "tool": "molecular_representation",
        "data": data,
        "error": None,
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "tool": "molecular_representation",
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _atoms_from_coordinates(
    coordinates: Any,
) -> list[dict[str, Any]]:
    """Normalize registry coordinates into a common atom representation."""

    if isinstance(coordinates, dict):
        atoms: list[dict[str, Any]] = []

        for label, value in coordinates.items():
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                raise ValueError(
                    f"Coordinate for {label!r} must contain 3 values."
                )

            # Keep the same element extraction convention as the generic
            # geometry symmetry engine.
            element = (
                "".join(ch for ch in str(label) if ch.isalpha())
                or str(label)
            )

            atoms.append(
                {
                    "index": len(atoms),
                    "label": str(label),
                    "element": element,
                    "coord": np.asarray(value, dtype=float),
                }
            )

        return atoms

    if isinstance(coordinates, list):
        atoms = []

        for index, atom in enumerate(coordinates):
            if isinstance(atom, dict):
                element = str(
                    atom.get("element")
                    or atom.get("symbol")
                    or "X"
                )

                coord = atom.get("coord")

                if coord is None:
                    coord = [
                        atom.get("x"),
                        atom.get("y"),
                        atom.get("z"),
                    ]

                label = str(atom.get("id", index))
            else:
                element, *coord = atom
                label = str(index)

            if not isinstance(coord, (list, tuple)) or len(coord) != 3:
                raise ValueError(
                    f"Atom {index} must contain a 3D coordinate."
                )

            atoms.append(
                {
                    "index": index,
                    "label": label,
                    "element": element,
                    "coord": np.asarray(coord, dtype=float),
                }
            )

        return atoms

    raise ValueError(
        "coordinates must be a mapping or list of atoms."
    )


def _build_atom_mapping(
    atoms: list[dict[str, Any]],
    matrix: np.ndarray,
    tolerance: float,
) -> dict[str, Any]:
    """Map every transformed atom to a unique equivalent original atom."""

    original = np.asarray(
        [atom["coord"] for atom in atoms],
        dtype=float,
    )

    transformed = (matrix @ original.T).T

    used: set[int] = set()
    mapping: list[dict[str, Any]] = []

    for source_index, atom in enumerate(atoms):
        candidates: list[tuple[float, int]] = []

        for target_index, target in enumerate(atoms):
            if target_index in used:
                continue

            if (
                target["element"].upper()
                != atom["element"].upper()
            ):
                continue

            distance = float(
                np.linalg.norm(
                    transformed[source_index]
                    - target["coord"]
                )
            )

            if distance <= tolerance:
                candidates.append(
                    (distance, target_index)
                )

        if not candidates:
            mapping.append(
                {
                    "from_index": source_index,
                    "from": atom["label"],
                    "element": atom["element"],
                    "to_index": None,
                    "match": None,
                    "distance": None,
                }
            )
            continue

        distance, target_index = min(candidates)

        used.add(target_index)

        mapping.append(
            {
                "from_index": source_index,
                "from": atom["label"],
                "element": atom["element"],
                "to_index": target_index,
                "match": atoms[target_index]["label"],
                "distance": distance,
            }
        )

    valid = (
        len(mapping) == len(atoms)
        and len(used) == len(atoms)
        and all(item["to_index"] is not None for item in mapping)
    )

    return {
        "is_valid": valid,
        "mapping": mapping,
        "transformed_coordinates": {
            atom["label"]: transformed[index].tolist()
            for index, atom in enumerate(atoms)
        },
    }


def _build_3n_matrix(
    matrix: np.ndarray,
    mapping: list[dict[str, Any]],
    atom_count: int,
) -> np.ndarray:
    """Construct the 3N x 3N displacement representation matrix.

    Basis convention:

        (x_1, y_1, z_1, x_2, y_2, z_2, ..., x_N, y_N, z_N)

    If operation g maps atom i -> atom j, the Cartesian displacement
    vector at atom i is transformed by the same 3x3 matrix M(g) and
    placed in the displacement block belonging to atom j.
    """

    dimension = 3 * atom_count
    representation = np.zeros(
        (dimension, dimension),
        dtype=float,
    )

    for item in mapping:
        source_index = item["from_index"]
        target_index = item["to_index"]

        if target_index is None:
            raise ValueError(
                "Cannot construct 3N representation from incomplete "
                "atom mapping."
            )

        source_slice = slice(
            3 * source_index,
            3 * source_index + 3,
        )

        target_slice = slice(
            3 * target_index,
            3 * target_index + 3,
        )

        representation[target_slice, source_slice] = matrix

    return representation


def _classify_characters(
    operations: list[dict[str, Any]],
    characters: dict[str, float],
    point_group_classes: list[str],
    class_sizes: dict[str, int],
) -> tuple[dict[str, str], dict[str, float]]:
    """Group individual operation characters into conjugacy classes."""

    operation_to_class: dict[str, str] = {}
    class_characters: dict[str, float] = {}

    raw_class_counts: dict[str, int] = {}
    for operation in operations:
        raw_class = str(
            operation.get("class") or operation.get("id") or ""
        ).strip()
        raw_class_counts[raw_class] = raw_class_counts.get(raw_class, 0) + 1

    # Resolve readable operation classes such as C3/sigma_v to the
    # canonical conjugacy-class symbols used by the point-group registry.
    #
    # The point-group class sizes are supplied by the caller through the
    # canonical class list.  No molecule-specific mapping is used here.
    resolved_classes: dict[str, str] = {}
    for raw_class, count in raw_class_counts.items():
        resolved_classes[raw_class] = resolve_operation_class(
            raw_class,
            point_group_classes,
            class_sizes,
            count,
        )

    for operation in operations:
        operation_id = str(operation.get("id", "")).strip()

        if not operation_id:
            raise ValueError(
                "Every operation must have a valid id."
            )

        raw_class = str(
            operation.get("class") or operation_id
        ).strip()

        class_symbol = resolved_classes[raw_class]

        if operation_id not in characters:
            raise ValueError(
                f"Character for operation {operation_id!r} is missing."
            )

        operation_to_class[operation_id] = class_symbol

        value = float(characters[operation_id])

        # All members of a symmetry class must have the same character.
        if class_symbol in class_characters:
            previous = class_characters[class_symbol]

            if not np.isclose(
                previous,
                value,
                atol=1e-6,
                rtol=1e-8,
            ):
                raise ValueError(
                    f"Characters are inconsistent within class "
                    f"{class_symbol!r}: {previous} vs {value}."
                )
        else:
            class_characters[class_symbol] = value

    missing = [
        class_symbol
        for class_symbol in point_group_classes
        if class_symbol not in class_characters
    ]

    if missing:
        raise ValueError(
            "Missing operations for point-group class(es): "
            + ", ".join(missing)
        )

    return operation_to_class, class_characters


def calculate_3n_representation(
    molecule: str | MoleculeDefinition,
    operations: list[dict[str, Any]] | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Calculate the universal 3N molecular displacement representation."""

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
            return _failure(
                "MOLECULE_NOT_REGISTERED",
                str(exc),
            )
        except Exception as exc:
            return _failure(
                "REGISTRY_ERROR",
                f"Molecule registry error: {exc}",
            )

    try:
        atoms = _atoms_from_coordinates(
            definition.coordinates
        )
    except Exception as exc:
        return _failure(
            "INVALID_GEOMETRY",
            str(exc),
        )

    atom_count = len(atoms)

    if atom_count == 0:
        return _failure(
            "EMPTY_MOLECULE",
            "Molecule contains no atoms.",
        )

    if operations is None:
        operations = definition.operations

    if not isinstance(operations, list) or not operations:
        return _failure(
            "INVALID_OPERATIONS",
            "operations must be a non-empty list.",
        )

    # Registered molecules use the normal symmetry engine.
    # External PubChem definitions already contain independently
    # verified operations and must not be resolved through the registry.
    if isinstance(molecule, MoleculeDefinition):
        verified_operations = list(operations or definition.operations)
        symmetry_data = {
            "point_group": definition.point_group,
        }

        if not verified_operations:
            return _failure(
                "NO_VERIFIED_OPERATIONS",
                "No verified symmetry operations were supplied.",
            )
    else:
        symmetry_result = analyze_symmetry(
            definition.molecule_id
        )

        if not symmetry_result.get("success"):
            return _failure(
                "SYMMETRY_ANALYSIS_FAILED",
                str(symmetry_result.get("error")),
            )

        symmetry_data = symmetry_result.get("data") or {}
        verified_operations = symmetry_data.get("operations") or []

        if not verified_operations:
            return _failure(
                "NO_VERIFIED_OPERATIONS",
                "No symmetry operations were returned by the "
                "generic symmetry engine.",
            )

    # Use the symmetry engine's operation definitions when available.
    # This keeps geometric verification and representation construction
    # on exactly the same operation schema.
    operation_by_id = {
        str(operation.get("id")): operation
        for operation in verified_operations
    }

    working_operations: list[dict[str, Any]] = []

    for operation in operations:
        operation_id = str(operation.get("id", "")).strip()

        if operation_id not in operation_by_id:
            return _failure(
                "OPERATION_NOT_VERIFIED",
                f"Operation {operation_id!r} was not returned "
                f"by the symmetry engine.",
            )

        verified = dict(operation_by_id[operation_id])

        if not verified.get("verified", False):
            return _failure(
                "INVALID_SYMMETRY_OPERATION",
                f"Operation {operation_id!r} is not a verified "
                f"symmetry operation.",
            )

        # Preserve the registry class declaration.
        if "class" in operation:
            verified["class"] = operation["class"]

        working_operations.append(verified)

    try:
        point_group_id = (
            symmetry_data.get("point_group")
            or definition.point_group
        )

        point_group = get_point_group(point_group_id)
    except Exception as exc:
        return _failure(
            "POINT_GROUP_NOT_REGISTERED",
            str(exc),
        )

    dimension = 3 * atom_count

    operation_matrices: dict[str, list[list[float]]] = {}
    representation_matrices: dict[str, list[list[float]]] = {}
    characters: dict[str, float] = {}
    mappings: dict[str, list[dict[str, Any]]] = {}

    for operation in working_operations:
        operation_id = str(operation["id"])

        built = build_transformation_matrix(operation)

        if not built.get("success"):
            return _failure(
                "MATRIX_BUILD_FAILED",
                f"Could not build M(g) for {operation_id}: "
                f"{built.get('error')}",
            )

        matrix = np.asarray(
            built["matrix"],
            dtype=float,
        )

        if matrix.shape != (3, 3):
            return _failure(
                "INVALID_CARTESIAN_MATRIX",
                f"M(g) for {operation_id} is not 3x3.",
            )

        mapping_result = _build_atom_mapping(
            atoms=atoms,
            matrix=matrix,
            tolerance=tolerance,
        )

        if not mapping_result["is_valid"]:
            return _failure(
                "ATOM_MAPPING_FAILED",
                f"Operation {operation_id} does not produce "
                "a valid one-to-one same-element atom mapping.",
            )

        mapping = mapping_result["mapping"]

        representation_matrix = _build_3n_matrix(
            matrix=matrix,
            mapping=mapping,
            atom_count=atom_count,
        )

        character = float(
            np.trace(representation_matrix)
        )

        operation_matrices[operation_id] = matrix.tolist()
        representation_matrices[operation_id] = (
            representation_matrix.tolist()
        )
        characters[operation_id] = (
            int(character)
            if float(character).is_integer()
            else character
        )
        mappings[operation_id] = mapping

    try:
        operation_to_class, class_characters = (
            _classify_characters(
                working_operations,
                characters,
                point_group.classes,
                point_group.class_sizes,
            )
        )

        reducible_characters = [
            class_characters[class_symbol]
            for class_symbol in point_group.classes
        ]

        reduction = reduce_representation(
            reducible_characters,
            point_group,
        )

        reduction["summary"] = format_reduction_summary(
            reduction
        )

    except Exception as exc:
        return _failure(
            "REDUCTION_FAILED",
            str(exc),
        )

    reconstructed_dimension = sum(
        reduction["multiplicities"][irrep]
        * point_group.irrep_dimensions[irrep]
        for irrep in point_group.irreps
    )

    if reconstructed_dimension != dimension:
        return _failure(
            "DIMENSION_MISMATCH",
            "Reduced representation dimension "
            f"{reconstructed_dimension} does not match "
            f"3N = {dimension}.",
        )

    return _success(
        {
            "molecule": {
                "id": definition.molecule_id,
                "name": definition.name,
                "formula": definition.formula,
                "point_group": point_group.point_group_id,
                "coordinates": definition.coordinates,
            },
            "representation_type": "3n_displacement",
            "atom_count": atom_count,
            "dimension": dimension,
            "basis": [
                f"{atom['label']}:{component}"
                for atom in atoms
                for component in ("x", "y", "z")
            ],
            "operations": working_operations,
            "cartesian_matrices": operation_matrices,
            "representation_matrices": representation_matrices,
            "mappings": mappings,
            "characters": characters,
            "group_theory": {
                "classes": list(point_group.classes),
                "class_characters": class_characters,
                "reducible_characters": reducible_characters,
                "operation_to_class": operation_to_class,
                "reduction": reduction,
            },
            "verification": {
                "dimension": dimension,
                "reduced_dimension": reconstructed_dimension,
                "dimension_match": (
                    reconstructed_dimension == dimension
                ),
                "all_operations_mapped": all(
                    all(
                        item["match"] is not None
                        for item in mapping
                    )
                    for mapping in mappings.values()
                ),
            },
        }
    )
