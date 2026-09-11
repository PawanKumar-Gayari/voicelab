"""
Generic full-analysis orchestration tool for VoiceLab.

This is the registry-driven counterpart to app.tools.bf3_analysis. Where
that module hard-codes BF3 geometry and the D3h character table, this
module works for ANY molecule registered in app.science.molecule_registry
whose point group is registered in app.science.point_group_registry.

Flow:
    molecule_registry
        -> molecule geometry + operations (each operation carries a
           "class" field identifying its conjugacy class)
    representation.py (existing, molecule-independent)
        -> M(g), D(g), chi(g)
    point_group_registry
        -> classes, character table, irreps for the molecule's point group
    reduction.py (new, point-group-independent)
        -> Gamma = sum a_i * irrep_i
    verification.py (existing, molecule-independent)
        -> independent verification

Dropping a new molecule file into app/science/molecules/ (with operations
tagged by conjugacy "class") and, if needed, a new point group file into
app/science/point_groups/ is enough for this tool to analyze it — no
change to this file, the voice agent, or any other molecule is required.

This module does not modify app.tools.bf3_analysis, app.science.bf3, or
app.science.d3h. The existing BF3 pipeline keeps working exactly as before.
"""

from __future__ import annotations

from typing import Any

from app.science.molecule_registry import get_molecule
from app.science.point_group_registry import get_point_group
from app.science.class_resolver import resolve_operation_class
from app.science.reduction import format_reduction_summary, reduce_representation
from app.tools.representation import calculate_representation
from app.tools.verification import verify_representation
from app.tools.symmetry import analyze_symmetry
from app.tools.vibrational_analysis import calculate_vibrational_analysis
from app.science.pubchem_production import analyze_external


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "tool": "full_analysis",
        "data": data,
        "error": None,
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "tool": "full_analysis",
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def analyze_molecule(
    molecule: str,
    basis: list[str] | None = None,
    include_vibrations: bool = False,
) -> dict[str, Any]:
    """
    Run the complete deterministic symmetry pipeline for any registered
    molecule: symmetry -> representation -> reduction -> verification.

    Parameters
    ----------
    molecule:
        Molecule id, name, or formula known to the Molecule Registry.
    basis:
        Cartesian basis functions. Defaults to x, y, z.
    include_vibrations:
        If True, additionally run the verified vibrational/IR/Raman
        analysis engine. Defaults to False so existing Cartesian
        analysis behavior remains unchanged.
    """
    if basis is None:
        basis = ["x", "y", "z"]

    if not isinstance(basis, list) or not all(
        isinstance(item, str) for item in basis
    ):
        return _failure("INVALID_BASIS", "basis must be a list of strings.")

    if not basis:
        return _failure(
            "INVALID_BASIS", "basis must contain at least one basis function."
        )

    # 1. Resolve the molecule from the registry.
    try:
        definition = get_molecule(molecule)
    except KeyError:
        # Registry-first architecture:
        # registered molecules continue through the existing deterministic
        # VoiceLab pipeline unchanged. Only an unknown molecule is eligible
        # for the external PubChem fallback.
        return analyze_external(
            molecule,
            basis=basis,
            include_vibrations=include_vibrations,
        )
    except Exception as exc:
        return _failure("REGISTRY_ERROR", f"Molecule registry error: {exc}")

    symmetry_result = analyze_symmetry(definition.molecule_id)
    if not symmetry_result.get("success"):
        return _failure("SYMMETRY_ANALYSIS_FAILED", str(symmetry_result.get("error")))

    symmetry_data = symmetry_result.get("data") or {}
    operations = symmetry_data.get("operations") or []
    inferred_point_group = symmetry_data.get("point_group")

    if not inferred_point_group:
        return _failure("POINT_GROUP_NOT_INFERRED", "Verified molecular geometry did not match a registered point-group signature.")

    if not operations:
        return _failure(
            "INVALID_MOLECULE_DATA",
            f"{definition.molecule_id} has no registered operations.",
        )

    # 2. Resolve the point group from the registry.
    try:
        point_group = get_point_group(inferred_point_group)
    except KeyError as exc:
        return _failure("POINT_GROUP_NOT_REGISTERED", str(exc))
    except Exception as exc:
        return _failure(
            "POINT_GROUP_REGISTRY_ERROR", f"Point group registry error: {exc}"
        )

    # 3. Existing, molecule-independent representation tool computes D(g), chi(g).
    representation_result = calculate_representation(
        molecule=definition.molecule_id,
        basis=basis,
        operations=operations,
    )

    if not representation_result.get("success"):
        return _failure(
            "REPRESENTATION_FAILED", str(representation_result.get("error"))
        )

    representation = representation_result.get("data", {})
    representation_matrices = representation.get("representation_matrices", {})
    characters = representation.get("characters", {})

    if not representation_matrices or not characters:
        return _failure(
            "INCOMPLETE_REPRESENTATION",
            "Representation matrices or characters are missing.",
        )

    # 4. Group each operation's character by its declared conjugacy class.
    #    This is the only per-molecule information the generic tool needs,
    #    and it comes from the molecule's own operation data, not a branch
    #    in this tool.
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
        try:
            resolved_classes[raw_class] = resolve_operation_class(
                raw_class,
                point_group.classes,
                point_group.class_sizes,
                count,
            )
        except ValueError as exc:
            return _failure("UNKNOWN_CLASS", str(exc))

    for operation in operations:
        operation_id = str(operation.get("id", ""))
        raw_class = str(
            operation.get("class") or operation_id
        ).strip()
        class_symbol = resolved_classes[raw_class]

        operation_to_class[operation_id] = class_symbol
        class_characters.setdefault(
            class_symbol, float(characters[operation_id])
        )

    missing_classes = [
        class_symbol
        for class_symbol in point_group.classes
        if class_symbol not in class_characters
    ]

    if missing_classes:
        return _failure(
            "INCOMPLETE_CLASSES",
            f"{definition.molecule_id} is missing operations for "
            f"{point_group.point_group_id} class(es): "
            f"{', '.join(missing_classes)}.",
        )

    reducible_characters = [
        class_characters[class_symbol] for class_symbol in point_group.classes
    ]

    # 5. Reduce the reducible representation into irreducible representations.
    try:
        reduction = reduce_representation(reducible_characters, point_group)
    except Exception as exc:
        return _failure("REDUCTION_FAILED", f"Failed to reduce representation: {exc}")

    reduction["summary"] = format_reduction_summary(reduction)

    # 6. Existing, molecule-independent verification tool remains the final gate.
    verification_result = verify_representation(
        molecule=definition.molecule_id,
        operations=operations,
        representation_matrices=representation_matrices,
        characters=characters,
    )

    if not verification_result.get("success"):
        return _failure(
            "VERIFICATION_FAILED", str(verification_result.get("error"))
        )

    verification = verification_result.get("data", {})

    vibrational_analysis = None

    if include_vibrations:
        try:
            vibrational_result = calculate_vibrational_analysis(
                definition.molecule_id
            )
        except Exception as exc:
            return _failure(
                "VIBRATIONAL_ANALYSIS_FAILED",
                f"Vibrational analysis failed: {exc}",
            )

        if not vibrational_result.get("success"):
            return _failure(
                "VIBRATIONAL_ANALYSIS_FAILED",
                str(vibrational_result.get("error")),
            )

        vibrational_analysis = vibrational_result.get("data")

    return _success(
        {
            "molecule": {
                "id": definition.molecule_id,
                "name": definition.name,
                "formula": definition.formula,
                "point_group": inferred_point_group,
                "coordinates": definition.coordinates,
            },
            "point_group": inferred_point_group,
            "declared_point_group": definition.point_group,
            "operations": operations,
            "basis": basis,
            "representation": representation,
            "group_theory": {
                "classes": point_group.classes,
                "character_table": point_group.character_table,
                "irreps": point_group.irreps,
                "irrep_dimensions": point_group.irrep_dimensions,
                "operation_to_class": operation_to_class,
                "reducible_characters": reducible_characters,
                "reduction": reduction,
            },
            "verification": verification,
            "symmetry_verification": symmetry_data.get("verification", {}),
            "vibrational_analysis": vibrational_analysis,
        }
    )
