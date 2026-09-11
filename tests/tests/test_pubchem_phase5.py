import numpy as np
from app.science.pubchem_principal_axes import (
    center_geometry, rotation_matrix, reflection_matrix,
    generate_principal_axis_candidates,
)
from app.science.pubchem_fallback import registry_first

def atoms():
    return [
        {"element":"O","coords":[0,0,0]},
        {"element":"H","coords":[0,0.757,0.587]},
        {"element":"H","coords":[0,-0.757,0.587]},
    ]

def test_centering():
    centered, center = center_geometry(atoms())
    assert np.allclose(np.mean([a["coords"] for a in centered], axis=0), 0)
    assert len(center) == 3

def test_rotation_is_orthogonal():
    m = rotation_matrix([0,0,1], 120)
    assert np.allclose(m.T @ m, np.eye(3), atol=1e-10)
    assert np.isclose(np.linalg.det(m), 1.0, atol=1e-10)

def test_reflection_is_improper():
    m = reflection_matrix([0,0,1])
    assert np.allclose(m.T @ m, np.eye(3), atol=1e-10)
    assert np.isclose(np.linalg.det(m), -1.0, atol=1e-10)

def test_candidates_include_identity_and_inversion():
    _, _, _, candidates = generate_principal_axis_candidates(atoms())
    types = {(c["type"], c["id"]) for c in candidates}
    assert ("identity","E") in types
    assert ("inversion","i") in types

def test_registry_first_preserves_local_path():
    calls=[]
    result = registry_first(
        "BF3",
        registry_has=lambda x: True,
        local_analyze=lambda x: calls.append("local") or {"success":True},
        external_analyze=lambda x: calls.append("external") or {"success":True},
    )
    assert calls == ["local"]
    assert result["success"]

def test_external_requires_verification():
    result = registry_first(
        "CO2",
        registry_has=lambda x: False,
        local_analyze=lambda x: {"success":True},
        external_analyze=lambda x: {"success":True,"data":{"verification":{"status":"FLAG"}}},
    )
    assert result["success"] is False
