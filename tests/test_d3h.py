"""
Tests for the VoiceLab D3h character-table module.

Coverage:
    - D3h class names and class sizes
    - class/order metadata
    - six irreducible representations
    - character-table values
    - irrep dimensions
    - standard basis-function assignments
    - representation reduction
    - reconstructed characters
    - character-table orthogonality
    - dimension-sum validation
    - complete D3h validation status
"""

from __future__ import annotations

import math

import pytest

from app.science.d3h import (
    D3H_BASIS_FUNCTIONS,
    D3H_CHARACTER_TABLE,
    D3H_CLASSES,
    D3H_CLASS_ORDERS,
    D3H_CLASS_SIZES,
    D3H_IRREP_DIMENSIONS,
    D3H_IRREPS,
    get_basis_functions,
    get_d3h_character_table,
    get_d3h_classes,
    get_d3h_data,
    get_irrep_characters,
    get_irrep_dimension,
    reduce_representation,
    validate_d3h_character_table,
)


EXPECTED_CLASSES = (
    "E",
    "2C3",
    "3C2'",
    "sigma_h",
    "2S3",
    "3sigma_v",
)

EXPECTED_CLASS_SIZES = {
    "E": 1,
    "2C3": 2,
    "3C2'": 3,
    "sigma_h": 1,
    "2S3": 2,
    "3sigma_v": 3,
}

EXPECTED_CLASS_ORDERS = {
    "E": 1,
    "2C3": 2,
    "3C2'": 3,
    "sigma_h": 1,
    "2S3": 2,
    "3sigma_v": 3,
}

EXPECTED_IRREPS = (
    "A1'",
    "A2'",
    "E'",
    "A1''",
    "A2''",
    "E''",
)

EXPECTED_DIMENSIONS = {
    "A1'": 1,
    "A2'": 1,
    "E'": 2,
    "A1''": 1,
    "A2''": 1,
    "E''": 2,
}

EXPECTED_CHARACTER_TABLE = {
    "A1'": (1, 1, 1, 1, 1, 1),
    "A2'": (1, 1, -1, 1, 1, -1),
    "E'": (2, -1, 0, 2, -1, 0),
    "A1''": (1, 1, 1, -1, -1, -1),
    "A2''": (1, 1, -1, -1, -1, 1),
    "E''": (2, -1, 0, -2, 1, 0),
}


# ---------------------------------------------------------------------------
# Class and group structure tests
# ---------------------------------------------------------------------------


def test_d3h_classes_have_expected_order_and_names() -> None:
    assert D3H_CLASSES == EXPECTED_CLASSES


def test_d3h_class_sizes_are_correct() -> None:
    assert D3H_CLASS_SIZES == EXPECTED_CLASS_SIZES
    assert sum(D3H_CLASS_SIZES.values()) == 12


def test_d3h_class_orders_are_correct() -> None:
    assert D3H_CLASS_ORDERS == EXPECTED_CLASS_ORDERS


def test_get_d3h_classes_returns_complete_metadata() -> None:
    classes = get_d3h_classes()

    assert len(classes) == 6

    for item in classes:
        symbol = item["symbol"]

        assert symbol in EXPECTED_CLASSES
        assert item["size"] == EXPECTED_CLASS_SIZES[symbol]
        assert item["order"] == EXPECTED_CLASS_ORDERS[symbol]


def test_d3h_has_six_irreducible_representations() -> None:
    assert D3H_IRREPS == EXPECTED_IRREPS
    assert len(D3H_IRREPS) == 6


# ---------------------------------------------------------------------------
# Character-table tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("irrep", "expected"),
    EXPECTED_CHARACTER_TABLE.items(),
)
def test_character_table_rows(
    irrep: str,
    expected: tuple[int, ...],
) -> None:
    assert D3H_CHARACTER_TABLE[irrep] == expected


def test_character_table_has_one_value_per_class() -> None:
    for irrep in D3H_IRREPS:
        assert len(D3H_CHARACTER_TABLE[irrep]) == len(D3H_CLASSES)


def test_get_d3h_character_table_contains_complete_data() -> None:
    table = get_d3h_character_table()

    assert table["group"] == "D3h"
    assert tuple(table["classes"]) == EXPECTED_CLASSES
    assert table["class_sizes"] == EXPECTED_CLASS_SIZES
    assert tuple(table["irreps"]) == EXPECTED_IRREPS
    assert table["dimensions"] == EXPECTED_DIMENSIONS

    for irrep in EXPECTED_IRREPS:
        assert tuple(table["characters"][irrep]) == EXPECTED_CHARACTER_TABLE[irrep]


def test_get_irrep_characters_returns_class_mapping() -> None:
    assert get_irrep_characters("E'") == {
        "E": 2,
        "2C3": -1,
        "3C2'": 0,
        "sigma_h": 2,
        "2S3": -1,
        "3sigma_v": 0,
    }


def test_unknown_irrep_character_lookup_fails() -> None:
    with pytest.raises(ValueError, match="Unknown D3h"):
        get_irrep_characters("B1")


# ---------------------------------------------------------------------------
# Irrep dimension tests
# ---------------------------------------------------------------------------


def test_irrep_dimensions_are_correct() -> None:
    assert D3H_IRREP_DIMENSIONS == EXPECTED_DIMENSIONS


@pytest.mark.parametrize(
    ("irrep", "dimension"),
    EXPECTED_DIMENSIONS.items(),
)
def test_get_irrep_dimension(
    irrep: str,
    dimension: int,
) -> None:
    assert get_irrep_dimension(irrep) == dimension


def test_unknown_irrep_dimension_lookup_fails() -> None:
    with pytest.raises(ValueError, match="Unknown D3h"):
        get_irrep_dimension("B1")


# ---------------------------------------------------------------------------
# Basis-function tests
# ---------------------------------------------------------------------------


def test_basis_functions_match_d3h_assignments() -> None:
    assert D3H_BASIS_FUNCTIONS["A1'"] == (
        "x^2 + y^2",
        "z^2",
    )

    assert D3H_BASIS_FUNCTIONS["A2'"] == ()

    assert D3H_BASIS_FUNCTIONS["E'"] == (
        "x",
        "y",
        "x^2 - y^2",
        "xy",
    )

    assert D3H_BASIS_FUNCTIONS["A1''"] == ()

    assert D3H_BASIS_FUNCTIONS["A2''"] == (
        "z",
    )

    assert D3H_BASIS_FUNCTIONS["E''"] == (
        "xz",
        "yz",
    )


@pytest.mark.parametrize(
    "irrep",
    EXPECTED_IRREPS,
)
def test_get_basis_functions_returns_list(irrep: str) -> None:
    result = get_basis_functions(irrep)

    assert isinstance(result, list)
    assert result == list(D3H_BASIS_FUNCTIONS[irrep])


def test_unknown_irrep_basis_lookup_fails() -> None:
    with pytest.raises(ValueError, match="Unknown D3h"):
        get_basis_functions("B1")


# ---------------------------------------------------------------------------
# Character-table orthogonality tests
# ---------------------------------------------------------------------------


def _weighted_character_inner_product(
    first: tuple[int, ...],
    second: tuple[int, ...],
) -> float:
    """Compute the D3h class-weighted character inner product."""
    group_order = sum(D3H_CLASS_SIZES.values())

    return sum(
        D3H_CLASS_SIZES[class_symbol]
        * first[index]
        * second[index]
        for index, class_symbol in enumerate(D3H_CLASSES)
    ) / group_order


def test_irrep_self_orthogonality() -> None:
    for irrep in D3H_IRREPS:
        value = _weighted_character_inner_product(
            D3H_CHARACTER_TABLE[irrep],
            D3H_CHARACTER_TABLE[irrep],
        )

        assert math.isclose(value, 1.0, abs_tol=1e-10)


def test_distinct_irreps_are_orthogonal() -> None:
    for index, first_irrep in enumerate(D3H_IRREPS):
        for second_irrep in D3H_IRREPS[index + 1:]:
            value = _weighted_character_inner_product(
                D3H_CHARACTER_TABLE[first_irrep],
                D3H_CHARACTER_TABLE[second_irrep],
            )

            assert math.isclose(value, 0.0, abs_tol=1e-10)


def test_orthogonality_matrix_is_identity() -> None:
    result = validate_d3h_character_table()

    orthogonality = result["orthogonality"]

    for first_irrep in D3H_IRREPS:
        for second_irrep in D3H_IRREPS:
            expected = 1.0 if first_irrep == second_irrep else 0.0

            assert math.isclose(
                orthogonality[first_irrep][second_irrep],
                expected,
                abs_tol=1e-10,
            )


# ---------------------------------------------------------------------------
# Representation reduction tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("characters", "expected_multiplicities", "expected_dimension"),
    [
        (
            [1, 1, 1, 1, 1, 1],
            {"A1'": 1, "A2'": 0, "E'": 0, "A1''": 0, "A2''": 0, "E''": 0},
            1,
        ),
        (
            [2, -1, 0, 2, -1, 0],
            {"A1'": 0, "A2'": 0, "E'": 1, "A1''": 0, "A2''": 0, "E''": 0},
            2,
        ),
        (
            [1, 1, -1, -1, -1, 1],
            {"A1'": 0, "A2'": 0, "E'": 0, "A1''": 0, "A2''": 1, "E''": 0},
            1,
        ),
        (
            [3, 0, -1, 1, -2, 1],
            {"A1'": 0, "A2'": 0, "E'": 1, "A1''": 0, "A2''": 1, "E''": 0},
            3,
        ),
    ],
)
def test_reduce_representation(
    characters: list[float],
    expected_multiplicities: dict[str, int],
    expected_dimension: int,
) -> None:
    result = reduce_representation(characters)

    assert result["group"] == "D3h"
    assert result["multiplicities"] == expected_multiplicities
    assert result["dimension"] == expected_dimension


def test_reduction_reconstructs_input_characters() -> None:
    characters = [3, 0, -1, 1, -2, 1]

    result = reduce_representation(characters)

    assert result["reconstructed_characters"] == characters


def test_reduction_of_zero_representation_is_zero() -> None:
    result = reduce_representation([0, 0, 0, 0, 0, 0])

    assert all(
        multiplicity == 0
        for multiplicity in result["multiplicities"].values()
    )

    assert result["dimension"] == 0
    assert result["reconstructed_characters"] == [0, 0, 0, 0, 0, 0]


def test_reduction_requires_six_class_characters() -> None:
    with pytest.raises(ValueError, match="exactly 6 values"):
        reduce_representation([1, 1, 1])


def test_reduction_rejects_non_numeric_characters() -> None:
    with pytest.raises(ValueError, match="numeric"):
        reduce_representation(["E", 1, 1, 1, 1, 1])


# ---------------------------------------------------------------------------
# Complete validation tests
# ---------------------------------------------------------------------------


def test_dimension_sum_equals_group_order() -> None:
    result = validate_d3h_character_table()

    assert result["group_order"] == 12
    assert result["dimension_sum"] == 12
    assert result["dimension_check"] is True


def test_character_table_validation_passes() -> None:
    result = validate_d3h_character_table()

    assert result["status"] == "PASS"
    assert result["dimension_check"] is True
    assert result["orthogonality_check"] is True


def test_get_d3h_data_contains_complete_validated_dataset() -> None:
    data = get_d3h_data()

    assert data["group"] == "D3h"
    assert data["group_order"] == 12
    assert len(data["classes"]) == 6
    assert tuple(data["irreps"]) == EXPECTED_IRREPS
    assert data["validation"]["status"] == "PASS"
    assert data["validation"]["dimension_check"] is True
    assert data["validation"]["orthogonality_check"] is True
