"""Universal vibrational representation and spectroscopy analysis.

Pipeline:
    Γ3N
      -> Γtrans
      -> Γrot
      -> Γvib
      -> irreducible reduction
      -> IR/Raman activity

No molecule-specific formulas are hard-coded here.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.science.molecule_registry import get_molecule, MoleculeDefinition
from app.science.point_group_registry import get_point_group
from app.science.class_resolver import resolve_operation_class
from app.science.reduction import reduce_representation, format_reduction_summary
from app.science.transformations import build_transformation_matrix
from app.tools.molecular_representation import calculate_3n_representation


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "tool": "vibrational_analysis",
        "data": data,
        "error": None,
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "tool": "vibrational_analysis",
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _class_characters(
    operations: list[dict[str, Any]],
    characters: dict[str, float],
    classes: list[str],
    class_sizes: dict[str, int],
    tolerance: float = 1e-8,
) -> tuple[dict[str, str], dict[str, float]]:
    operation_to_class: dict[str, str] = {}
    class_characters: dict[str, float] = {}

    raw_class_counts: dict[str, int] = {}
    for operation in operations:
        raw_class = str(
            operation.get("class") or operation.get("id") or ""
        ).strip()
        raw_class_counts[raw_class] = raw_class_counts.get(raw_class, 0) + 1

    resolved_classes: dict[str, str] = {}
    for raw_class, count in raw_class_counts.items():
        resolved_classes[raw_class] = resolve_operation_class(
            raw_class,
            classes,
            class_sizes,
            count,
        )

    for operation in operations:
        operation_id = str(operation.get("id", "")).strip()
        raw_class = str(
            operation.get("class") or operation_id
        ).strip()
        class_symbol = resolved_classes[raw_class]

        if operation_id not in characters:
            raise ValueError(
                f"Character for operation {operation_id!r} is missing."
            )

        value = float(characters[operation_id])
        operation_to_class[operation_id] = class_symbol

        if class_symbol in class_characters:
            if not np.isclose(
                class_characters[class_symbol],
                value,
                atol=tolerance,
                rtol=tolerance,
            ):
                raise ValueError(
                    f"Characters are inconsistent within class "
                    f"{class_symbol!r}."
                )
        else:
            class_characters[class_symbol] = value

    missing = [c for c in classes if c not in class_characters]
    if missing:
        raise ValueError(
            "Missing point-group classes: " + ", ".join(missing)
        )

    return operation_to_class, class_characters


def _reduce(
    characters: list[float],
    point_group: Any,
) -> dict[str, Any]:
    result = reduce_representation(characters, point_group)
    result["summary"] = format_reduction_summary(result)
    return result


def _operation_characters(
    operations: list[dict[str, Any]],
    builder,
) -> dict[str, float]:
    characters: dict[str, float] = {}

    for operation in operations:
        operation_id = str(operation["id"])
        result = build_transformation_matrix(operation)

        if not result.get("success"):
            raise ValueError(
                f"Could not build transformation matrix for "
                f"{operation_id}: {result.get('error')}"
            )

        matrix = np.asarray(result["matrix"], dtype=float)

        if matrix.shape != (3, 3):
            raise ValueError(
                f"Transformation matrix for {operation_id} is not 3x3."
            )

        representation = builder(matrix)
        characters[operation_id] = float(np.trace(representation))

    return characters


def _translation_matrix(matrix: np.ndarray) -> np.ndarray:
    """Translations transform as ordinary Cartesian vectors."""
    return matrix


def _rotation_matrix(matrix: np.ndarray) -> np.ndarray:
    """Rotations transform as axial vectors.

    R' = det(M) M R
    """
    return float(np.linalg.det(matrix)) * matrix


def _activity_irreps(
    operations: list[dict[str, Any]],
    point_group: Any,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Derive IR and Raman active irreps universally.

    IR:
        determined from the Cartesian translation/vector representation.

    Raman:
        determined from the symmetric-square representation of the
        Cartesian vector representation:

            chi_Raman(g) =
                [chi_vec(g)^2 + chi_vec(g^2)] / 2

        This is the representation carried by the six quadratic
        Cartesian functions:
            x^2, y^2, z^2, xy, xz, yz

    No molecule-specific or point-group-specific activity rules
    are hard-coded here.
    """

    classes = list(point_group.classes)

    # -----------------------------
    # Vector / translation representation
    # -----------------------------
    vector_operation_chars: dict[str, float] = {}

    # -----------------------------
    # Raman symmetric-square representation
    # -----------------------------
    raman_operation_chars: dict[str, float] = {}

    for operation in operations:
        operation_id = str(operation["id"])

        result = build_transformation_matrix(operation)

        if not result.get("success"):
            raise ValueError(
                f"Could not build transformation matrix for "
                f"{operation_id}: {result.get('error')}"
            )

        matrix = np.asarray(result["matrix"], dtype=float)

        if matrix.shape != (3, 3):
            raise ValueError(
                f"Transformation matrix for {operation_id} is not 3x3."
            )

        chi_vec = float(np.trace(matrix))

        # Character of g^2 in the vector representation.
        matrix_squared = matrix @ matrix
        chi_vec_squared = float(np.trace(matrix_squared))

        chi_raman = (
            chi_vec * chi_vec + chi_vec_squared
        ) / 2.0

        vector_operation_chars[operation_id] = chi_vec
        raman_operation_chars[operation_id] = chi_raman

    vector_to_class, vector_class_chars = _class_characters(
        operations,
        vector_operation_chars,
        classes,
        point_group.class_sizes,
        tolerance=tolerance,
    )

    raman_to_class, raman_class_chars = _class_characters(
        operations,
        raman_operation_chars,
        classes,
        point_group.class_sizes,
        tolerance=tolerance,
    )

    vector_chars = [
        vector_class_chars[class_symbol]
        for class_symbol in classes
    ]

    raman_chars = [
        raman_class_chars[class_symbol]
        for class_symbol in classes
    ]

    vector_reduction = _reduce(
        vector_chars,
        point_group,
    )

    raman_reduction = _reduce(
        raman_chars,
        point_group,
    )

    # IR-active irreps are exactly those appearing in the
    # Cartesian vector/translation representation.
    ir_active_irreps = [
        irrep
        for irrep in point_group.irreps
        if vector_reduction["multiplicities"].get(irrep, 0) > 0
    ]

    # Raman-active irreps are exactly those appearing in
    # the quadratic Cartesian representation.
    raman_active_irreps = [
        irrep
        for irrep in point_group.irreps
        if raman_reduction["multiplicities"].get(irrep, 0) > 0
    ]

    return {
        "vector": {
            "operation_characters": vector_operation_chars,
            "characters": vector_chars,
            "operation_to_class": vector_to_class,
            "reduction": vector_reduction,
        },
        "raman": {
            "operation_characters": raman_operation_chars,
            "characters": raman_chars,
            "operation_to_class": raman_to_class,
            "reduction": raman_reduction,
        },
        "ir_active_irreps": ir_active_irreps,
        "raman_active_irreps": raman_active_irreps,
    }


def _mode_summary(
    reduction: dict[str, Any],
    point_group: Any,
    ir_active_irreps: list[str],
    raman_active_irreps: list[str],
) -> list[dict[str, Any]]:
    """Build spectroscopy activity metadata for vibrational irreps."""

    modes = []

    for irrep in point_group.irreps:
        multiplicity = reduction["multiplicities"].get(irrep, 0)

        if not multiplicity:
            continue

        dimension = point_group.irrep_dimensions[irrep]

        modes.append(
            {
                "irrep": irrep,
                "multiplicity": multiplicity,
                "degeneracy": dimension,
                "normal_coordinates": multiplicity * dimension,
                "ir_active": irrep in ir_active_irreps,
                "raman_active": irrep in raman_active_irreps,
                "basis_functions": point_group.basis_functions.get(
                    irrep, []
                ),
            }
        )

    return modes


def calculate_vibrational_analysis(
    molecule: str | MoleculeDefinition,
) -> dict[str, Any]:
    """Calculate Γ3N, Γtrans, Γrot, Γvib and spectroscopy activity."""

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
        except Exception as exc:
            return _failure(
                "MOLECULE_NOT_REGISTERED",
                str(exc),
            )

    # 1. Already validated universal 3N calculation.
    if isinstance(molecule, MoleculeDefinition):
        verification_tolerances = {
            float(operation.get("_verification_tolerance", 1e-7))
            for operation in definition.operations
        }

        if len(verification_tolerances) != 1:
            return _failure(
                "INVALID_OPERATION_TOLERANCE",
                "External operations do not share one verification tolerance.",
            )

        verification_tolerance = next(iter(verification_tolerances))

        three_n_result = calculate_3n_representation(
            definition,
            operations=definition.operations,
            tolerance=verification_tolerance,
        )
    else:
        three_n_result = calculate_3n_representation(
            definition.molecule_id
        )

    if not three_n_result.get("success"):
        return _failure(
            "THREE_N_FAILED",
            str(three_n_result.get("error")),
        )

    three_n = three_n_result["data"]
    operations = three_n["operations"]

    try:
        point_group = get_point_group(
            three_n["molecule"]["point_group"]
        )

        classes = list(point_group.classes)

        # 2. Translation representation.
        trans_operation_chars = _operation_characters(
            operations,
            _translation_matrix,
        )

        trans_to_class, trans_class_chars = _class_characters(
            operations,
            trans_operation_chars,
            classes,
            point_group.class_sizes,
            tolerance=verification_tolerance if isinstance(molecule, MoleculeDefinition) else 1e-8,
        )

        trans_chars = [
            trans_class_chars[c]
            for c in classes
        ]

        trans_reduction = _reduce(
            trans_chars,
            point_group,
        )

        # 3. Rotation representation.
        rot_operation_chars = _operation_characters(
            operations,
            _rotation_matrix,
        )

        rot_to_class, rot_class_chars = _class_characters(
            operations,
            rot_operation_chars,
            classes,
            point_group.class_sizes,
            tolerance=verification_tolerance if isinstance(molecule, MoleculeDefinition) else 1e-8,
        )

        rot_chars = [
            rot_class_chars[c]
            for c in classes
        ]

        rot_reduction = _reduce(
            rot_chars,
            point_group,
        )

        # 4. Vibrational characters:
        #
        # Γvib = Γ3N - Γtrans - Γrot
        three_n_chars = [
            float(value)
            for value in three_n["group_theory"]["reducible_characters"]
        ]

        vib_chars = [
            three_n_chars[i]
            - trans_chars[i]
            - rot_chars[i]
            for i in range(len(classes))
        ]

        vib_reduction = _reduce(
            vib_chars,
            point_group,
        )

        # 5. Dimension verification.
        atom_count = three_n["atom_count"]
        three_n_dimension = 3 * atom_count
        vib_dimension = sum(
            vib_reduction["multiplicities"][irrep]
            * point_group.irrep_dimensions[irrep]
            for irrep in point_group.irreps
        )

        expected_vib_dimension = 3 * atom_count - 6

        dimension_match = (
            vib_dimension == expected_vib_dimension
        )

        # 6. Spectroscopic activity.
        #
        # First determine which irreps are spectroscopically active
        # for the point group, then restrict those lists to irreps
        # that actually occur in the vibrational representation.
        # This keeps the reported activity specific to Gamma_vib
        # rather than reporting active irreps absent from the molecule's
        # vibrational modes.
        activity = _activity_irreps(
            operations,
            point_group,
            tolerance=verification_tolerance if isinstance(molecule, MoleculeDefinition) else 1e-8,
        )

        vibrational_irreps = {
            irrep
            for irrep in point_group.irreps
            if vib_reduction["multiplicities"].get(irrep, 0) > 0
        }

        activity["ir_active_irreps"] = [
            irrep
            for irrep in activity["ir_active_irreps"]
            if irrep in vibrational_irreps
        ]

        activity["raman_active_irreps"] = [
            irrep
            for irrep in activity["raman_active_irreps"]
            if irrep in vibrational_irreps
        ]

        modes = _mode_summary(
            vib_reduction,
            point_group,
            activity["ir_active_irreps"],
            activity["raman_active_irreps"],
        )

        return _success(
            {
                "molecule": three_n["molecule"],
                "point_group": point_group.point_group_id,
                "atom_count": atom_count,
                "dimensions": {
                    "3n": three_n_dimension,
                    "expected_vibrational": expected_vib_dimension,
                    "vibrational": vib_dimension,
                },
                "classes": classes,
                "representations": {
                    "3n": {
                        "characters": three_n_chars,
                        "reduction": three_n["group_theory"]["reduction"],
                    },
                    "translations": {
                        "characters": trans_chars,
                        "operation_characters": trans_operation_chars,
                        "operation_to_class": trans_to_class,
                        "reduction": trans_reduction,
                    },
                    "rotations": {
                        "characters": rot_chars,
                        "operation_characters": rot_operation_chars,
                        "operation_to_class": rot_to_class,
                        "reduction": rot_reduction,
                    },
                    "vibrations": {
                        "characters": vib_chars,
                        "reduction": vib_reduction,
                    },
                },
                "vibrational_modes": modes,
                "activity": activity,
                "verification": {
                    "three_n_dimension": three_n_dimension,
                    "vibrational_dimension": vib_dimension,
                    "expected_vibrational_dimension":
                        expected_vib_dimension,
                    "dimension_match": dimension_match,
                    "translation_dimension":
                        trans_reduction["dimension"],
                    "rotation_dimension":
                        rot_reduction["dimension"],
                    "subtraction_identity": all(
                        np.isclose(
                            three_n_chars[i],
                            trans_chars[i]
                            + rot_chars[i]
                            + vib_chars[i],
                            atol=1e-8,
                            rtol=1e-8,
                        )
                        for i in range(len(classes))
                    ),
                },
            }
        )

    except Exception as exc:
        return _failure(
            "VIBRATIONAL_ANALYSIS_FAILED",
            str(exc),
        )
