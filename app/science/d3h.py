"""
D3h character table and irreducible-representation data for VoiceLab.

This module contains reusable D3h group-theory data only.

It does not contain BF3 geometry, Cartesian transformation matrices,
AI logic, frontend logic, or molecule-specific calculations.

D3h classes used throughout VoiceLab:

    E
    2C3
    3C2'
    sigma_h
    2S3
    3sigma_v

Character convention:

    rows    -> irreducible representations
    columns -> D3h conjugacy classes

The ordering of classes is fixed and must remain consistent with the
BF3 operation ordering used by the science layer.
"""

from __future__ import annotations

from typing import Any


D3H_NAME = "D3h"

# ---------------------------------------------------------------------------
# Conjugacy classes
# ---------------------------------------------------------------------------

D3H_CLASSES: tuple[str, ...] = (
    "E",
    "2C3",
    "3C2'",
    "sigma_h",
    "2S3",
    "3sigma_v",
)

D3H_CLASS_ORDERS: dict[str, int] = {
    "E": 1,
    "2C3": 2,
    "3C2'": 3,
    "sigma_h": 1,
    "2S3": 2,
    "3sigma_v": 3,
}

D3H_CLASS_SIZES: dict[str, int] = {
    "E": 1,
    "2C3": 2,
    "3C2'": 3,
    "sigma_h": 1,
    "2S3": 2,
    "3sigma_v": 3,
}

# ---------------------------------------------------------------------------
# Irreducible representations
# ---------------------------------------------------------------------------

D3H_IRREPS: tuple[str, ...] = (
    "A1'",
    "A2'",
    "E'",
    "A1''",
    "A2''",
    "E''",
)

D3H_IRREP_DIMENSIONS: dict[str, int] = {
    "A1'": 1,
    "A2'": 1,
    "E'": 2,
    "A1''": 1,
    "A2''": 1,
    "E''": 2,
}

# Character table:
#
#             E   2C3  3C2'  sigma_h  2S3  3sigma_v
# A1'         1    1    1      1       1      1
# A2'         1    1   -1      1       1     -1
# E'          2   -1    0      2      -1      0
# A1''        1    1    1     -1      -1     -1
# A2''        1    1   -1     -1      -1      1
# E''         2   -1    0     -2       1      0

D3H_CHARACTER_TABLE: dict[str, tuple[int, ...]] = {
    "A1'": (1, 1, 1, 1, 1, 1),
    "A2'": (1, 1, -1, 1, 1, -1),
    "E'": (2, -1, 0, 2, -1, 0),
    "A1''": (1, 1, 1, -1, -1, -1),
    "A2''": (1, 1, -1, -1, -1, 1),
    "E''": (2, -1, 0, -2, 1, 0),
}

# ---------------------------------------------------------------------------
# Basis functions
# ---------------------------------------------------------------------------

# Common Cartesian and quadratic basis-function assignments for D3h.
# These are descriptive group-theory data; calculations using a basis
# remain the responsibility of the representation/science layers.
D3H_BASIS_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "A1'": (
        "x^2 + y^2",
        "z^2",
    ),
    "A2'": (),
    "E'": (
        "x",
        "y",
        "x^2 - y^2",
        "xy",
    ),
    "A1''": (),
    "A2''": (
        "z",
    ),
    "E''": (
        "xz",
        "yz",
    ),
}

# ---------------------------------------------------------------------------
# Character-table access
# ---------------------------------------------------------------------------


def get_d3h_classes() -> list[dict[str, Any]]:
    """Return D3h conjugacy-class metadata in fixed order."""
    return [
        {
            "symbol": symbol,
            "size": D3H_CLASS_SIZES[symbol],
            "order": D3H_CLASS_ORDERS[symbol],
        }
        for symbol in D3H_CLASSES
    ]


def get_d3h_character_table() -> dict[str, Any]:
    """
    Return the complete D3h character table.

    The returned structure is JSON-friendly and preserves the fixed
    class/irrep ordering used by VoiceLab.
    """
    return {
        "group": D3H_NAME,
        "classes": list(D3H_CLASSES),
        "class_sizes": D3H_CLASS_SIZES.copy(),
        "irreps": list(D3H_IRREPS),
        "dimensions": D3H_IRREP_DIMENSIONS.copy(),
        "characters": {
            irrep: list(D3H_CHARACTER_TABLE[irrep])
            for irrep in D3H_IRREPS
        },
        "basis_functions": {
            irrep: list(D3H_BASIS_FUNCTIONS[irrep])
            for irrep in D3H_IRREPS
        },
    }


def get_irrep_characters(
    irrep: str,
) -> dict[str, int]:
    """
    Return the character row for one D3h irreducible representation.
    """
    if not isinstance(irrep, str):
        raise ValueError("irrep must be a string.")

    normalized = irrep.strip()

    if normalized not in D3H_CHARACTER_TABLE:
        raise ValueError(
            f"Unknown D3h irreducible representation: {irrep!r}."
        )

    return {
        class_symbol: D3H_CHARACTER_TABLE[normalized][index]
        for index, class_symbol in enumerate(D3H_CLASSES)
    }


def get_basis_functions(
    irrep: str,
) -> list[str]:
    """Return the standard basis functions associated with one irrep."""
    if not isinstance(irrep, str):
        raise ValueError("irrep must be a string.")

    normalized = irrep.strip()

    if normalized not in D3H_BASIS_FUNCTIONS:
        raise ValueError(
            f"Unknown D3h irreducible representation: {irrep!r}."
        )

    return list(D3H_BASIS_FUNCTIONS[normalized])


def get_irrep_dimension(
    irrep: str,
) -> int:
    """Return the dimension of one D3h irreducible representation."""
    if not isinstance(irrep, str):
        raise ValueError("irrep must be a string.")

    normalized = irrep.strip()

    if normalized not in D3H_IRREP_DIMENSIONS:
        raise ValueError(
            f"Unknown D3h irreducible representation: {irrep!r}."
        )

    return D3H_IRREP_DIMENSIONS[normalized]


# ---------------------------------------------------------------------------
# Representation reduction
# ---------------------------------------------------------------------------


def reduce_representation(
    reducible_characters: list[float],
) -> dict[str, Any]:
    """
    Reduce a D3h reducible representation into irreducible representations.

    Reduction formula:

        a_i = (1 / h) * sum_R n_R chi_Gamma(R) chi_i(R)

    where:
        h = order of the group = 12
        n_R = size of the conjugacy class
        chi_Gamma = reducible-representation character
        chi_i = irreducible-representation character

    The input character vector must follow D3H_CLASSES ordering.
    """
    if not isinstance(reducible_characters, list):
        raise ValueError("reducible_characters must be a list.")

    if len(reducible_characters) != len(D3H_CLASSES):
        raise ValueError(
            "reducible_characters must contain exactly "
            f"{len(D3H_CLASSES)} values in D3h class order."
        )

    try:
        gamma = [float(value) for value in reducible_characters]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "reducible_characters must contain numeric values."
        ) from exc

    import math

    group_order = sum(D3H_CLASS_SIZES.values())
    multiplicities: dict[str, int] = {}
    raw_multiplicities: dict[str, float] = {}

    for irrep in D3H_IRREPS:
        characters = D3H_CHARACTER_TABLE[irrep]

        numerator = sum(
            D3H_CLASS_SIZES[class_symbol]
            * gamma[index]
            * characters[index]
            for index, class_symbol in enumerate(D3H_CLASSES)
        )

        coefficient = numerator / group_order
        raw_multiplicities[irrep] = coefficient

        nearest = round(coefficient)

        if math.isclose(coefficient, nearest, abs_tol=1e-10, rel_tol=1e-10):
            multiplicities[irrep] = int(nearest)
        else:
            raise ValueError(
                f"Reduction coefficient for {irrep} is not an integer: "
                f"{coefficient:.12g}"
            )

    reconstructed = [
        sum(
            multiplicities[irrep]
            * D3H_CHARACTER_TABLE[irrep][index]
            for irrep in D3H_IRREPS
        )
        for index in range(len(D3H_CLASSES))
    ]

    dimension = sum(
        multiplicities[irrep] * D3H_IRREP_DIMENSIONS[irrep]
        for irrep in D3H_IRREPS
    )

    return {
        "group": D3H_NAME,
        "classes": list(D3H_CLASSES),
        "reducible_characters": [
            int(value) if float(value).is_integer() else float(value)
            for value in gamma
        ],
        "multiplicities": multiplicities,
        "raw_multiplicities": raw_multiplicities,
        "reconstructed_characters": reconstructed,
        "dimension": dimension,
        "formula": (
            "a_i = (1/h) Σ_R n_R χ_Γ(R) χ_i(R), h = 12"
        ),
    }


# ---------------------------------------------------------------------------
# Character-table validation
# ---------------------------------------------------------------------------


def validate_d3h_character_table() -> dict[str, Any]:
    """
    Validate the D3h character table using orthogonality relations.

    For irreps i and j:

        (1/h) Σ_R n_R χ_i(R) χ_j(R) = δ_ij

    The function also verifies the dimension sum:

        Σ_i d_i^2 = h = 12
    """
    group_order = sum(D3H_CLASS_SIZES.values())

    dimension_sum = sum(
        dimension * dimension
        for dimension in D3H_IRREP_DIMENSIONS.values()
    )

    orthogonality: dict[str, dict[str, float]] = {}

    for irrep_i in D3H_IRREPS:
        orthogonality[irrep_i] = {}

        for irrep_j in D3H_IRREPS:
            value = sum(
                D3H_CLASS_SIZES[class_symbol]
                * D3H_CHARACTER_TABLE[irrep_i][index]
                * D3H_CHARACTER_TABLE[irrep_j][index]
                for index, class_symbol in enumerate(D3H_CLASSES)
            ) / group_order

            orthogonality[irrep_i][irrep_j] = value

    orthogonality_pass = all(
        abs(
            orthogonality[irrep_i][irrep_j]
            - (1.0 if irrep_i == irrep_j else 0.0)
        ) <= 1e-10
        for irrep_i in D3H_IRREPS
        for irrep_j in D3H_IRREPS
    )

    dimension_pass = dimension_sum == group_order

    return {
        "group": D3H_NAME,
        "group_order": group_order,
        "dimension_sum": dimension_sum,
        "dimension_check": dimension_pass,
        "orthogonality": orthogonality,
        "orthogonality_check": orthogonality_pass,
        "status": "PASS"
        if dimension_pass and orthogonality_pass
        else "FLAG",
    }


def get_d3h_data() -> dict[str, Any]:
    """Return all reusable D3h group-theory data."""
    validation = validate_d3h_character_table()

    return {
        "group": D3H_NAME,
        "group_order": sum(D3H_CLASS_SIZES.values()),
        "classes": get_d3h_classes(),
        "irreps": list(D3H_IRREPS),
        "dimensions": D3H_IRREP_DIMENSIONS.copy(),
        "character_table": get_d3h_character_table(),
        "validation": validation,
    }
