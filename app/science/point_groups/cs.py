"""Cs point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "Cs"


def get_point_group_data() -> dict:
    """Return Cs character-table data using the registry-standard interface."""
    return {
        "id": POINT_GROUP_ID,
        "order": 2,
        "classes": ["E", "sigma_h"],
        "class_sizes": {"E": 1, "sigma_h": 1},
        "irreps": ["A'", "A''"],
        "irrep_dimensions": {"A'": 1, "A''": 1},
        "character_table": {
            "A'": [1, 1],
            "A''": [1, -1],
        },
        "basis_functions": {
            "A'": ["x", "y", "Rz"],
            "A''": ["z", "Rx", "Ry"],
        },
    }
