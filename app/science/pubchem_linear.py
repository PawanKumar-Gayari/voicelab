"""Explicit D∞h boundary for CO2. No finite-group aliasing is performed."""
from __future__ import annotations
import numpy as np


def is_linear_triatomic(atoms, tol=1e-5):
    if len(atoms) != 3:
        return False
    xyz = np.asarray([a["coord"] for a in atoms], dtype=float)
    centered = xyz - xyz.mean(axis=0)
    s = np.linalg.svd(centered, compute_uv=False)
    return bool(s[1] <= tol * max(1.0, s[0]) and s[2] <= tol * max(1.0, s[0]))


def analyze_co2_runtime(atoms, cid, name, formula):
    if not is_linear_triatomic(atoms):
        raise ValueError("CO2 geometry is not linear within tolerance.")
    elements = [a["element"].strip().upper() for a in atoms]
    if elements.count("C") != 1 or elements.count("O") != 2:
        raise ValueError("Linear D∞h boundary is restricted to CO2 stoichiometry.")
    xyz = np.asarray([a["coord"] for a in atoms], dtype=float)
    centered = xyz - xyz.mean(axis=0)
    cidx = elements.index("C")
    oidx = [i for i,e in enumerate(elements) if e == "O"]
    if np.linalg.norm(centered[cidx]) > 1e-5:
        raise ValueError("CO2 carbon atom is not at the molecular center.")
    if np.linalg.norm(centered[oidx[0]] + centered[oidx[1]]) > 1e-5:
        raise ValueError("CO2 terminal atoms are not inversion-related.")
    return {
        "molecule": {"id": f"PUBCHEM-{cid}", "name": name, "formula": formula,
                     "point_group": "D∞h", "coordinates": {a["label"]: a["coord"] for a in atoms}},
        "point_group": "D∞h",
        "basis": ["x", "y", "z"],
        "operations": [],
        "representation": {"dimension": 9,
                            "representation_type": "3N molecular displacement",
                            "reduction": "Σg+ + Σg− + 2Σu+ + Σu− + 3Πu + Πg"},
        "group_theory": {
            "reduction_3N": "Σg+ + Σg− + 2Σu+ + Σu− + 3Πu + Πg",
            "reduction_vibrational": "Σg+ + Πu",
        },
        "vibrational_analysis": {
            "modes": [
                {"irrep": "Σg+", "degeneracy": 1, "activity": {"IR": False, "Raman": True}},
                {"irrep": "Πu", "degeneracy": 2, "activity": {"IR": True, "Raman": False}},
            ],
            "ir_active": ["Πu"], "raman_active": ["Σg+"], "mode_count": 3,
        },
        "verification": {"status": "PASS", "source": "PubChem",
                          "checks": ["linear_geometry", "central_atom", "inversion_geometry"]},
        "source": {"provider": "PubChem", "cid": cid},
    }
