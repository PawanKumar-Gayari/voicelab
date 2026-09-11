from app.science.molecule_registry import (
    get_molecule,
    list_molecules,
    refresh_molecule_registry,
)


def test_bf3_is_auto_registered():
    molecule = get_molecule("BF3")
    assert molecule.molecule_id == "BF3"
    assert molecule.name == "BF3"
    assert molecule.formula == "BF3"
    assert molecule.point_group == "D3h"


def test_h2o_is_auto_discovered():
    molecule = get_molecule("H2O")

    assert molecule.molecule_id == "H2O"
    assert molecule.name == "H2O"
    assert molecule.formula == "H2O"
    assert molecule.point_group == "C2v"
    assert len(molecule.operations) == 4


def test_molecule_aliases_work():
    assert get_molecule("BF3").molecule_id == "BF3"
    assert get_molecule("bf3").molecule_id == "BF3"
    assert get_molecule(" BF3 ").molecule_id == "BF3"

    assert get_molecule("H2O").molecule_id == "H2O"
    assert get_molecule("h2o").molecule_id == "H2O"
    assert get_molecule(" H2O ").molecule_id == "H2O"


def test_registry_lists_both_molecules():
    molecules = list_molecules()
    by_id = {item["id"]: item for item in molecules}

    assert {"BF3", "H2O"} <= set(by_id)
    assert by_id["BF3"]["name"] == "BF3"
    assert by_id["BF3"]["point_group"] == "D3h"
    assert by_id["H2O"]["name"] == "H2O"
    assert by_id["H2O"]["formula"] == "H2O"
    assert by_id["H2O"]["point_group"] == "C2v"


def test_refresh_keeps_both_molecules_discovered():
    refresh_molecule_registry()
    molecules = {item["id"] for item in list_molecules()}

    assert "BF3" in molecules
    assert "H2O" in molecules
