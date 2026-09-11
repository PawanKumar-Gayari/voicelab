"""C3v point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "C3v"


def get_point_group_data() -> dict:
    """Return C3v character-table data using the registry-standard interface."""
    return {
        "id": POINT_GROUP_ID,
        "order": 6,
        "classes": ["E", "2C3", "3sigma_v"],
        "class_sizes": {"E": 1, "2C3": 2, "3sigma_v": 3},
        "irreps": ["A1", "A2", "E"],
        "irrep_dimensions": {"A1": 1, "A2": 1, "E": 2},
        "character_table": {
            "A1": [1, 1, 1],
            "A2": [1, 1, -1],
            "E": [2, -1, 0],
        },
        "basis_functions": {
            "A1": ["z"],
            "A2": ["Rz"],
            "E": ["(x, y)", "(Rx, Ry)"],
        },
    }
