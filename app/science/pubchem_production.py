"""Production fallback entry point. Registered molecules always stay local."""
from __future__ import annotations
from typing import Any
from app.science.molecule_registry import registry
from app.science.pubchem_client import fetch_3d
from app.science.geometry_normalizer import normalize_atoms
from app.science.pubchem_linear import is_linear_triatomic, analyze_co2_runtime
from app.science.pubchem_runtime import analyze_external_finite


def analyze_external(molecule: str, *, basis: list[str], include_vibrations: bool = False) -> dict[str, Any]:
    record = fetch_3d(molecule)
    atoms = normalize_atoms(record.atoms)
    if is_linear_triatomic(atoms):
        elements = [a["element"].upper() for a in atoms]
        if elements.count("C") == 1 and elements.count("O") == 2:
            data = analyze_co2_runtime(atoms, record.cid, record.name, record.formula)
            if not include_vibrations:
                data["vibrational_analysis"] = None
            return {"success": True, "tool": "full_analysis", "data": data, "error": None}
        raise ValueError("Linear external geometry is not supported by the current D∞h boundary.")
    data = analyze_external_finite(
        molecule,
        basis=basis,
        include_vibrations=include_vibrations,
    )
    return {"success": True, "tool": "full_analysis", "data": data, "error": None}


def registry_first_external(
    molecule: str, *, local_analyze, basis: list[str], include_vibrations: bool,
) -> dict[str, Any]:
    if registry.has(molecule):
        return local_analyze(molecule, basis=basis, include_vibrations=include_vibrations)
    try:
        result = analyze_external(molecule, basis=basis, include_vibrations=include_vibrations)
        if (result.get("data") or {}).get("verification", {}).get("status") != "PASS":
            raise ValueError("External result failed final verification gate.")
        return result
    except Exception as exc:
        return {"success": False, "tool": "full_analysis", "data": None,
                "error": {"code": "PUBCHEM_FALLBACK_FAILED", "message": str(exc)}}
