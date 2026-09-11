"""D3h point group character-table data for the Point Group Registry.

This mirrors the values already used by app.science.d3h (the BF3-specific
pipeline). It is defined independently here so the generic Point Group
Registry does not depend on, or modify, that existing module.
"""

POINT_GROUP_ID = "D3h"


def get_point_group_data() -> dict:
    """Return D3h character-table data using the registry-standard interface."""
    classes = ["E", "2C3", "3C2'", "sigma_h", "2S3", "3sigma_v"]

    return {
        "id": POINT_GROUP_ID,
        "order": 12,
        "classes": classes,
        "class_sizes": {
            "E": 1,
            "2C3": 2,
            "3C2'": 3,
            "sigma_h": 1,
            "2S3": 2,
            "3sigma_v": 3,
        },
        "irreps": ["A1'", "A2'", "E'", "A1''", "A2''", "E''"],
        "irrep_dimensions": {
            "A1'": 1,
            "A2'": 1,
            "E'": 2,
            "A1''": 1,
            "A2''": 1,
            "E''": 2,
        },
        "character_table": {
            "A1'": [1, 1, 1, 1, 1, 1],
            "A2'": [1, 1, -1, 1, 1, -1],
            "E'": [2, -1, 0, 2, -1, 0],
            "A1''": [1, 1, 1, -1, -1, -1],
            "A2''": [1, 1, -1, -1, -1, 1],
            "E''": [2, -1, 0, -2, 1, 0],
        },
        "basis_functions": {
            "A1'": [],
            "A2'": ["Rz"],
            "E'": ["(x, y)"],
            "A1''": [],
            "A2''": ["z"],
            "E''": ["(Rx, Ry)"],
        },
    }
