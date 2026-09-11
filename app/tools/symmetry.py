"""Registry-driven molecular symmetry tool.

The registry supplies molecule metadata and operation definitions.
Cartesian matrices are generated only by the universal transformation engine.
There is no molecule-specific branch in this tool.
"""

from __future__ import annotations

from typing import Any

from app.science.molecule_registry import get_molecule
from app.science.transformations import build_transformation_matrix
from app.science.geometry_symmetry import check_operation
from app.science.point_group_registry import registry as point_group_registry
from app.science.class_resolver import resolve_operation_class


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "tool": "symmetry",
        "data": data,
        "error": None,
    }


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "tool": "symmetry",
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
    }


def analyze_symmetry(molecule: str) -> dict[str, Any]:
    """Resolve a registered molecule and build all Cartesian M(g) matrices."""
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

    operations: list[dict[str, Any]] = []
    matrices: dict[str, list[list[float]]] = {}
    verified_classes: dict[str, int] = {}

    for index, source_operation in enumerate(definition.operations):
        if not isinstance(source_operation, dict):
            return _failure(
                "INVALID_OPERATION",
                f"Operation at index {index} must be a dictionary.",
            )

        operation = dict(source_operation)
        operation_id = str(operation.get("id", "")).strip()
        if not operation_id:
            return _failure(
                "INVALID_OPERATION_ID",
                f"Operation at index {index} has no valid id.",
            )

        result = build_transformation_matrix(operation)
        if not result["success"]:
            return _failure(
                "INVALID_OPERATION",
                (
                    f"Could not build M(g) for {operation_id}: "
                    f"{result['error']['message']}"
                ),
            )

        matrix = result["matrix"]
        geometric = check_operation(definition.coordinates, operation)
        operation["matrix"] = matrix
        operation["verified"] = bool(geometric.get("is_symmetry"))
        operation["verification"] = {
            "status": "PASS" if geometric.get("is_symmetry") else "FAIL",
            "mapping": geometric.get("mapping", []),
        }
        operations.append(operation)
        matrices[operation_id] = matrix
        if operation.get("verified") and operation.get("class"):
            class_name = str(operation["class"])
            verified_classes[class_name] = verified_classes.get(class_name, 0) + 1

    # Infer the point group from the verified operation-class signature.
    #
    # Operation definitions may use base symbols such as C3/sigma_v,
    # while the registry stores canonical conjugacy-class symbols such as
    # 2C3/3sigma_v. Resolve each candidate independently so inference
    # remains completely generic and does not depend on molecule names.
    inferred_point_group = None
    candidates = []

    for pg in point_group_registry._definitions.values():
        raw_counts = dict(verified_classes)
        canonical_counts: dict[str, int] = {}

        try:
            for raw_class, count in raw_counts.items():
                canonical = resolve_operation_class(
                    raw_class,
                    pg.classes,
                    pg.class_sizes,
                    int(count),
                )
                canonical_counts[canonical] = (
                    canonical_counts.get(canonical, 0) + int(count)
                )
        except ValueError:
            continue

        if (
            all(
                canonical_counts.get(cls, 0) == int(size)
                for cls, size in pg.class_sizes.items()
            )
            and sum(canonical_counts.values()) == pg.order
        ):
            candidates.append(pg.point_group_id)
    if len(candidates) == 1:
        inferred_point_group = candidates[0]

    return _success(
        {
            "molecule": definition.molecule_id,
            "formula": definition.formula,
            "point_group": inferred_point_group,
            "declared_point_group": definition.point_group,
            "coordinates": definition.coordinates,
            "operations": operations,
            "matrices": matrices,
            "verification": {
                "status": "PASS" if inferred_point_group else "FLAG",
                "verified_operation_count": sum(verified_classes.values()),
                "class_counts": verified_classes,
                "point_group": inferred_point_group,
            },
        }
    )
