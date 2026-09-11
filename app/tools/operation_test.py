"""Generic scientific test for an arbitrary candidate symmetry operation."""
from __future__ import annotations
from typing import Any
from app.science.molecule_registry import get_molecule
from app.science.geometry_symmetry import check_operation


def run_molecule_operation(molecule: str, operation: dict[str, Any]) -> dict[str, Any]:
    try:
        definition = get_molecule(molecule)
    except KeyError as exc:
        return {"success": False, "tool": "operation_test", "data": None, "error": {"code": "MOLECULE_NOT_REGISTERED", "message": str(exc)}}
    result = check_operation(definition.coordinates, operation)
    if not result["success"]:
        return {"success": False, "tool": "operation_test", "data": result, "error": result.get("error")}
    return {
        "success": True,
        "tool": "operation_test",
        "data": {
            "molecule": definition.molecule_id,
            "operation": result["operation"],
            "matrix": result["matrix"],
            "is_symmetry": result["is_symmetry"],
            "transformed_coordinates": result["transformed_coordinates"],
            "mapping": result["mapping"],
            "tolerance": result["tolerance"],
        },
        "error": None,
    }
