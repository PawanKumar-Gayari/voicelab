"""Td point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "Td"


def get_point_group_data() -> dict:
    """Return Td character-table data using the registry-standard interface."""
    classes = ["E", "8C3", "3C2", "6S4", "6sigma_d"]

    return {
        "id": POINT_GROUP_ID,
        "order": 24,
        "classes": classes,
        "class_sizes": {
            "E": 1,
            "8C3": 8,
            "3C2": 3,
            "6S4": 6,
            "6sigma_d": 6,
        },
        "irreps": ["A1", "A2", "E", "T1", "T2"],
        "irrep_dimensions": {
            "A1": 1,
            "A2": 1,
            "E": 2,
            "T1": 3,
            "T2": 3,
        },
        "character_table": {
            "A1": [1, 1, 1, 1, 1],
            "A2": [1, 1, 1, -1, -1],
            "E": [2, -1, 2, 0, 0],
            "T1": [3, 0, -1, 1, -1],
            "T2": [3, 0, -1, -1, 1],
        },
        "basis_functions": {
            "A1": [],
            "A2": [],
            "E": [],
            "T1": ["(Rx, Ry, Rz)"],
            "T2": ["(x, y, z)"],
        },
    }
