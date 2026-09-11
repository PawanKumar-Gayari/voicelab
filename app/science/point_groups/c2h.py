"""C2h point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "C2h"


def get_point_group_data() -> dict:
    """Return C2h character-table data using the registry-standard interface."""
    return {
        "id": POINT_GROUP_ID,
        "order": 4,
        "classes": ["E", "C2", "i", "sigma_h"],
        "class_sizes": {"E": 1, "C2": 1, "i": 1, "sigma_h": 1},
        "irreps": ["Ag", "Bg", "Au", "Bu"],
        "irrep_dimensions": {"Ag": 1, "Bg": 1, "Au": 1, "Bu": 1},
        "character_table": {
            "Ag": [1, 1, 1, 1],
            "Bg": [1, -1, 1, -1],
            "Au": [1, 1, -1, -1],
            "Bu": [1, -1, -1, 1],
        },
        "basis_functions": {
            "Ag": ["Rz"],
            "Bg": ["Rx", "Ry"],
            "Au": ["z"],
            "Bu": ["x", "y"],
        },
    }
