import pytest

from app.science.point_group_registry import (
    get_point_group,
    list_point_groups,
    refresh_point_group_registry,
    registry,
)


def test_registry_discovers_expected_point_groups():
    ids = {item["id"] for item in list_point_groups()}

    assert {
        "C1",
        "Cs",
        "Ci",
        "C2",
        "C2v",
        "C3v",
        "C2h",
        "D2h",
        "D3h",
        "Td",
    } <= ids


def test_registry_has_no_discovery_errors():
    assert registry.errors() == {}


def test_c2v_matches_h2o_class_layout():
    point_group = get_point_group("C2v")

    assert point_group.order == 4
    assert point_group.classes == [
        "E",
        "C2",
        "sigma_v(xz)",
        "sigma_v(yz)",
    ]
    assert set(point_group.irreps) == {"A1", "A2", "B1", "B2"}
    assert point_group.character_table["A1"] == [1.0, 1.0, 1.0, 1.0]
    assert point_group.character_table["B2"] == [1.0, -1.0, -1.0, 1.0]


def test_d3h_matches_bf3_class_layout():
    point_group = get_point_group("D3h")

    assert point_group.order == 12
    assert point_group.classes == [
        "E",
        "2C3",
        "3C2'",
        "sigma_h",
        "2S3",
        "3sigma_v",
    ]
    assert point_group.class_sizes["2C3"] == 2
    assert point_group.class_sizes["3sigma_v"] == 3


def test_td_order_and_dimension_consistency():
    point_group = get_point_group("Td")

    assert point_group.order == 24
    assert sum(point_group.class_sizes.values()) == 24
    assert sum(d**2 for d in point_group.irrep_dimensions.values()) == 24


def test_unregistered_point_group_raises_key_error():
    with pytest.raises(KeyError):
        get_point_group("Oh")


def test_case_insensitive_lookup():
    assert get_point_group("c2v").point_group_id == "C2v"
    assert get_point_group(" D3H ").point_group_id == "D3h"


def test_refresh_returns_current_list():
    molecules = refresh_point_group_registry()
    assert any(item["id"] == "C2v" for item in molecules)
