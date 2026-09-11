from app.tools.representation import calculate_representation
from app.tools.symmetry import analyze_symmetry
from app.tools.verification import verify_representation


def test_registry_pipeline_h2o():
    symmetry = analyze_symmetry("H2O")

    assert symmetry["success"] is True
    assert symmetry["data"]["point_group"] == "C2v"
    assert len(symmetry["data"]["operations"]) == 4

    representation = calculate_representation(
        molecule="H2O",
        basis=["x", "y", "z"],
        operations=symmetry["data"]["operations"],
    )

    assert representation["success"] is True
    data = representation["data"]

    assert data["characters"] == {
        "E": 3.0,
        "C2": -1.0,
        "sigma_v_xz": 1.0,
        "sigma_v_yz": 1.0,
    }

    verification = verify_representation(
        molecule="H2O",
        operations=symmetry["data"]["operations"],
        representation_matrices=data["representation_matrices"],
        characters=data["characters"],
    )

    assert verification["success"] is True
    assert verification["data"]["status"] == "PASS"


def test_registry_pipeline_bf3():
    symmetry = analyze_symmetry("BF3")

    assert symmetry["success"] is True
    assert symmetry["data"]["point_group"] == "D3h"
    assert len(symmetry["data"]["operations"]) == 12

    representation = calculate_representation(
        molecule="BF3",
        basis=["x", "y", "z"],
        operations=symmetry["data"]["operations"],
    )

    assert representation["success"] is True
    assert representation["data"]["characters"]["E"] == 3.0

    verification = verify_representation(
        molecule="BF3",
        operations=symmetry["data"]["operations"],
        representation_matrices=representation["data"]["representation_matrices"],
        characters=representation["data"]["characters"],
    )

    assert verification["success"] is True
    assert verification["data"]["status"] == "PASS"
