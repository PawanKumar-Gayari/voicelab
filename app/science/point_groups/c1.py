"""C1 point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "C1"


def get_point_group_data() -> dict:
    """Return C1 character-table data using the registry-standard interface."""
    return {
        "id": POINT_GROUP_ID,
        "order": 1,
        "classes": ["E"],
        "class_sizes": {"E": 1},
        "irreps": ["A"],
        "irrep_dimensions": {"A": 1},
        "character_table": {
            "A": [1],
        },
        "basis_functions": {
            "A": ["x", "y", "z", "Rx", "Ry", "Rz"],
        },
    }
