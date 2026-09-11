"""BF3 molecule adapter for the automatic Molecule Registry.

The actual BF3 scientific implementation remains in app.science.bf3.
This adapter only exposes the standard registry interface.
"""

from app.science.bf3 import get_bf3_symmetry_data

MOLECULE_ID = "BF3"

# Maps each BF3 operation id (from app.science.bf3, untouched) onto the
# D3h conjugacy class it belongs to. This lets the generic, registry-driven
# analysis tool group operations into classes for any molecule without a
# molecule-specific branch in the tool itself.
_D3H_OPERATION_CLASS = {
    "E": "E",
    "C3_1": "2C3",
    "C3_2": "2C3",
    "C2p_1": "3C2'",
    "C2p_2": "3C2'",
    "C2p_3": "3C2'",
    "sigma_h": "sigma_h",
    "S3_1": "2S3",
    "S3_2": "2S3",
    "sigma_v_1": "3sigma_v",
    "sigma_v_2": "3sigma_v",
    "sigma_v_3": "3sigma_v",
}


def _with_class(operation: dict) -> dict:
    enriched = dict(operation)
    operation_id = str(enriched.get("id", ""))
    enriched["class"] = _D3H_OPERATION_CLASS.get(operation_id, operation_id)
    return enriched


def get_molecule_data() -> dict:
    """Return BF3 data using the registry-standard interface."""
    data = get_bf3_symmetry_data()
    molecule_data = data.get("molecule", {})

    return {
        "id": MOLECULE_ID,
        "name": molecule_data.get("name", "BF3"),
        "formula": molecule_data.get("formula", "BF3"),
        "point_group": molecule_data.get("point_group", "D3h"),
        "coordinates": molecule_data.get("coordinates", {}),
        "operations": [
            _with_class(operation) for operation in data.get("operations", [])
        ],
        "matrices": data.get("matrices", {}),
    }
