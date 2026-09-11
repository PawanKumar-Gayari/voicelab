"""Regression tests for BF3, H2O, and NH3 molecular science results."""

from __future__ import annotations

import pytest

from app.tools.molecular_representation import calculate_3n_representation
from app.tools.symmetry import analyze_symmetry
from app.tools.vibrational_analysis import calculate_vibrational_analysis


EXPECTED = {
    "BF3": {
        "point_group": "D3h",
        "three_n": "Gamma = A1' + A2' + 3E' + 2A2'' + E''",
        "vibrational": "Gamma = A1' + 2E' + A2''",
        "ir": {"E'", "A2''"},
        "raman": {"A1'", "E'"},
        "three_n_dimension": 12,
        "vibrational_dimension": 6,
    },
    "H2O": {
        "point_group": "C2v",
        "three_n": "Gamma = 3A1 + A2 + 2B1 + 3B2",
        "vibrational": "Gamma = 2A1 + B2",
        "ir": {"A1", "B2"},
        "raman": {"A1", "B2"},
        "three_n_dimension": 9,
        "vibrational_dimension": 3,
    },
    "NH3": {
        "point_group": "C3v",
        "three_n": "Gamma = 3A1 + A2 + 4E",
        "vibrational": "Gamma = 2A1 + 2E",
        "ir": {"A1", "E"},
        "raman": {"A1", "E"},
        "three_n_dimension": 12,
        "vibrational_dimension": 6,
    },
}


@pytest.mark.parametrize("molecule", EXPECTED)
def test_point_group_regression(molecule: str) -> None:
    result = analyze_symmetry(molecule)

    assert result["success"] is True

    data = result["data"]
    expected = EXPECTED[molecule]

    assert data["point_group"] == expected["point_group"]
    assert data["declared_point_group"] == expected["point_group"]

    verification = data["verification"]
    assert verification["status"] == "PASS"


@pytest.mark.parametrize("molecule", EXPECTED)
def test_3n_representation_regression(molecule: str) -> None:
    result = calculate_3n_representation(molecule)

    assert result["success"] is True

    data = result["data"]
    expected = EXPECTED[molecule]

    reduction = data["group_theory"]["reduction"]

    assert reduction["group"] == expected["point_group"]
    assert reduction["summary"] == expected["three_n"]
    assert reduction["dimension"] == expected["three_n_dimension"]
    assert data["dimension"] == expected["three_n_dimension"]

    verification = data["verification"]

    assert verification["dimension"] == expected["three_n_dimension"]
    assert verification["reduced_dimension"] == expected["three_n_dimension"]
    assert verification["dimension_match"] is True
    assert verification["all_operations_mapped"] is True


@pytest.mark.parametrize("molecule", EXPECTED)
def test_vibrational_representation_regression(molecule: str) -> None:
    result = calculate_vibrational_analysis(molecule)

    assert result["success"] is True

    data = result["data"]
    expected = EXPECTED[molecule]

    assert data["point_group"] == expected["point_group"]

    reduction = data["representations"]["vibrations"]["reduction"]

    assert reduction["group"] == expected["point_group"]
    assert reduction["summary"] == expected["vibrational"]
    assert reduction["dimension"] == expected["vibrational_dimension"]

    assert data["dimensions"]["vibrational"] == expected["vibrational_dimension"]


@pytest.mark.parametrize("molecule", EXPECTED)
def test_ir_raman_activity_regression(molecule: str) -> None:
    result = calculate_vibrational_analysis(molecule)

    assert result["success"] is True

    data = result["data"]
    expected = EXPECTED[molecule]
    activity = data["activity"]

    assert set(activity["ir_active_irreps"]) == expected["ir"]
    assert set(activity["raman_active_irreps"]) == expected["raman"]

    modes = {
        mode["irrep"]: mode
        for mode in data["vibrational_modes"]
    }

    for irrep in expected["ir"]:
        assert modes[irrep]["ir_active"] is True

    for irrep in expected["raman"]:
        assert modes[irrep]["raman_active"] is True
