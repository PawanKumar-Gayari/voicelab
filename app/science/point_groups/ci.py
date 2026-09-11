"""Ci point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "Ci"


def get_point_group_data() -> dict:
    """Return Ci character-table data using the registry-standard interface."""
    return {
        "id": POINT_GROUP_ID,
        "order": 2,
        "classes": ["E", "i"],
        "class_sizes": {"E": 1, "i": 1},
        "irreps": ["Ag", "Au"],
        "irrep_dimensions": {"Ag": 1, "Au": 1},
        "character_table": {
            "Ag": [1, 1],
            "Au": [1, -1],
        },
        "basis_functions": {
            "Ag": ["Rx", "Ry", "Rz"],
            "Au": ["x", "y", "z"],
        },
    }
