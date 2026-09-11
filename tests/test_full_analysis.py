from app.tools.full_analysis import analyze_molecule


def test_full_analysis_bf3_end_to_end():
    result = analyze_molecule("BF3")

    assert result["success"] is True
    data = result["data"]

    assert data["point_group"] == "D3h"
    assert data["verification"]["status"] == "PASS"

    group_theory = data["group_theory"]
    assert group_theory["classes"] == [
        "E",
        "2C3",
        "3C2'",
        "sigma_h",
        "2S3",
        "3sigma_v",
    ]
    assert group_theory["reduction"]["multiplicities"]["E'"] == 1
    assert group_theory["reduction"]["multiplicities"]["A2''"] == 1
    assert group_theory["reduction"]["dimension"] == 3


def test_full_analysis_h2o_end_to_end():
    result = analyze_molecule("H2O")

    assert result["success"] is True
    data = result["data"]

    assert data["point_group"] == "C2v"
    assert data["verification"]["status"] == "PASS"

    reduction = data["group_theory"]["reduction"]
    assert reduction["multiplicities"] == {
        "A1": 1,
        "A2": 0,
        "B1": 1,
        "B2": 1,
    }
    assert reduction["summary"] == "Gamma = A1 + B1 + B2"


def test_full_analysis_case_insensitive_and_alias_lookup():
    result = analyze_molecule("h2o")
    assert result["success"] is True
    assert result["data"]["molecule"]["id"] == "H2O"


def test_full_analysis_unregistered_molecule_uses_external_provider():
    result = analyze_molecule("CH4")

    assert result["success"] is True
    assert result["data"]["molecule"]["formula"] == "CH4"
    assert result["data"]["point_group"] == "Td"
    assert result["data"]["representation"]["dimension"] == 15
    assert result["data"]["representation"]["reduction"] == (
        "Gamma = A1 + E + T1 + 3T2"
    )
    assert result["data"]["verification"]["status"] == "PASS"
    assert result["data"]["source"]["provider"] == "PubChem"


def test_full_analysis_default_basis_is_xyz():
    result = analyze_molecule("H2O")

    assert result["data"]["basis"] == ["x", "y", "z"]


def test_full_analysis_rejects_invalid_basis():
    result = analyze_molecule("H2O", basis=[])

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_BASIS"


def test_full_analysis_operations_carry_class_field():
    result = analyze_molecule("BF3")
    operations = result["data"]["operations"]

    classes_present = {op["class"] for op in operations}
    assert classes_present == {
        "E",
        "2C3",
        "3C2'",
        "sigma_h",
        "2S3",
        "3sigma_v",
    }
