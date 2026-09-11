"""
Generic irreducible-representation reduction.

This module contains no molecule-specific or point-group-specific data.
It reduces any reducible representation, for any point group registered
in app.science.point_group_registry, using the standard formula:

    n_i = (1/h) * sum_C  g_C * chi_Gamma(C) * chi_i(C)

where:
    h       = order of the group
    g_C     = size of conjugacy class C
    chi_Gamma(C) = reducible-representation character for class C
    chi_i(C)     = irreducible-representation character for class C

This generalizes the D3h-only reduction previously available in
app.science.d3h.reduce_representation, without changing that module.
"""

from __future__ import annotations

import math
from typing import Any

from app.science.point_group_registry import PointGroupDefinition


def reduce_representation(
    reducible_characters: list[float],
    point_group: PointGroupDefinition,
) -> dict[str, Any]:
    """
    Reduce a reducible representation into irreducible representations.

    Parameters
    ----------
    reducible_characters:
        Character values, one per conjugacy class, in the exact order
        of ``point_group.classes``.
    point_group:
        A resolved PointGroupDefinition from the Point Group Registry.

    Returns
    -------
    dict
        group, classes, reducible_characters, multiplicities,
        raw_multiplicities, reconstructed_characters, dimension,
        irrep_basis_functions, formula.
    """
    if not isinstance(reducible_characters, list):
        raise ValueError("reducible_characters must be a list.")

    classes = point_group.classes

    if len(reducible_characters) != len(classes):
        raise ValueError(
            "reducible_characters must contain exactly "
            f"{len(classes)} values in {point_group.point_group_id} "
            "class order: " + ", ".join(classes)
        )

    try:
        gamma = [float(value) for value in reducible_characters]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "reducible_characters must contain numeric values."
        ) from exc

    group_order = point_group.order
    multiplicities: dict[str, int] = {}
    raw_multiplicities: dict[str, float] = {}

    for irrep in point_group.irreps:
        characters = point_group.character_table[irrep]

        numerator = sum(
            point_group.class_sizes[class_symbol] * gamma[index] * characters[index]
            for index, class_symbol in enumerate(classes)
        )

        coefficient = numerator / group_order
        raw_multiplicities[irrep] = coefficient

        nearest = round(coefficient)

        if math.isclose(coefficient, nearest, abs_tol=1e-6, rel_tol=1e-8):
            multiplicities[irrep] = int(nearest)
        else:
            raise ValueError(
                f"Reduction coefficient for {irrep} is not an integer: "
                f"{coefficient:.12g}. Check that reducible_characters and "
                f"the {point_group.point_group_id} class order match."
            )

    reconstructed = [
        sum(
            multiplicities[irrep] * point_group.character_table[irrep][index]
            for irrep in point_group.irreps
        )
        for index in range(len(classes))
    ]

    dimension = sum(
        multiplicities[irrep] * point_group.irrep_dimensions[irrep]
        for irrep in point_group.irreps
    )

    irrep_basis_functions = {
        irrep: point_group.basis_functions.get(irrep, [])
        for irrep in point_group.irreps
        if multiplicities.get(irrep, 0) > 0
    }

    return {
        "group": point_group.point_group_id,
        "classes": list(classes),
        "reducible_characters": [
            int(value) if float(value).is_integer() else value for value in gamma
        ],
        "multiplicities": multiplicities,
        "raw_multiplicities": raw_multiplicities,
        "reconstructed_characters": reconstructed,
        "dimension": dimension,
        "irrep_basis_functions": irrep_basis_functions,
        "formula": (
            "n_i = (1/h) * sum_C g_C * chi_Gamma(C) * chi_i(C), "
            f"h = {group_order}"
        ),
    }


def format_reduction_summary(reduction: dict[str, Any]) -> str:
    """
    Build a compact human/voice-readable Gamma decomposition string.

    Example:
        "Gamma = 2A1 + B1 + B2"
    """
    multiplicities = reduction.get("multiplicities", {})

    terms = [
        (f"{count}{irrep}" if count != 1 else irrep)
        for irrep, count in multiplicities.items()
        if count
    ]

    if not terms:
        return "Gamma = 0"

    return "Gamma = " + " + ".join(terms)
