import pytest

from app.science.point_group_registry import get_point_group
from app.science.reduction import format_reduction_summary, reduce_representation


def test_reduce_h2o_translations_in_c2v():
    point_group = get_point_group("C2v")

    # Gamma(xyz) for H2O in C2v, in class order E, C2, sigma_v(xz), sigma_v(yz)
    reducible_characters = [3.0, -1.0, 1.0, 1.0]

    reduction = reduce_representation(reducible_characters, point_group)

    assert reduction["multiplicities"] == {
        "A1": 1,
        "A2": 0,
        "B1": 1,
        "B2": 1,
    }
    assert reduction["dimension"] == 3
    assert reduction["reconstructed_characters"] == reducible_characters
    assert format_reduction_summary(reduction) == "Gamma = A1 + B1 + B2"


def test_reduce_bf3_translations_in_d3h():
    point_group = get_point_group("D3h")

    # Gamma(xyz) for BF3 in D3h, class order E, 2C3, 3C2', sigma_h, 2S3, 3sigma_v
    reducible_characters = [3.0, 0.0, -1.0, 1.0, -2.0, 1.0]

    reduction = reduce_representation(reducible_characters, point_group)

    assert reduction["multiplicities"]["E'"] == 1
    assert reduction["multiplicities"]["A2''"] == 1
    assert reduction["dimension"] == 3
    assert format_reduction_summary(reduction) == "Gamma = E' + A2''"


def test_reduce_rejects_wrong_length():
    point_group = get_point_group("C2v")

    with pytest.raises(ValueError):
        reduce_representation([1.0, 2.0], point_group)


def test_reduce_rejects_non_integer_coefficients():
    point_group = get_point_group("C2v")

    # Not a valid representation of C2v (arbitrary noise), should not reduce
    # to integer multiplicities.
    with pytest.raises(ValueError):
        reduce_representation([1.0, 0.3, 0.0, 0.0], point_group)


def test_format_reduction_summary_handles_zero_representation():
    point_group = get_point_group("C2v")

    reduction = reduce_representation([0.0, 0.0, 0.0, 0.0], point_group)

    assert format_reduction_summary(reduction) == "Gamma = 0"
