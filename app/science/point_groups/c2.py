"""C2 point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "C2"


def get_point_group_data() -> dict:
    """Return C2 character-table data using the registry-standard interface."""
    return {
        "id": POINT_GROUP_ID,
        "order": 2,
        "classes": ["E", "C2"],
        "class_sizes": {"E": 1, "C2": 1},
        "irreps": ["A", "B"],
        "irrep_dimensions": {"A": 1, "B": 1},
        "character_table": {
            "A": [1, 1],
            "B": [1, -1],
        },
        "basis_functions": {
            "A": ["z", "Rz"],
            "B": ["x", "y", "Rx", "Ry"],
        },
    }
