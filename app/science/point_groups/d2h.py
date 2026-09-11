"""D2h point group character-table data for the Point Group Registry."""

POINT_GROUP_ID = "D2h"


def get_point_group_data() -> dict:
    """Return D2h character-table data using the registry-standard interface."""
    classes = [
        "E",
        "C2(z)",
        "C2(y)",
        "C2(x)",
        "i",
        "sigma(xy)",
        "sigma(xz)",
        "sigma(yz)",
    ]

    return {
        "id": POINT_GROUP_ID,
        "order": 8,
        "classes": classes,
        "class_sizes": {symbol: 1 for symbol in classes},
        "irreps": [
            "Ag",
            "B1g",
            "B2g",
            "B3g",
            "Au",
            "B1u",
            "B2u",
            "B3u",
        ],
        "irrep_dimensions": {
            "Ag": 1,
            "B1g": 1,
            "B2g": 1,
            "B3g": 1,
            "Au": 1,
            "B1u": 1,
            "B2u": 1,
            "B3u": 1,
        },
        "character_table": {
            "Ag": [1, 1, 1, 1, 1, 1, 1, 1],
            "B1g": [1, 1, -1, -1, 1, 1, -1, -1],
            "B2g": [1, -1, 1, -1, 1, -1, 1, -1],
            "B3g": [1, -1, -1, 1, 1, -1, -1, 1],
            "Au": [1, 1, 1, 1, -1, -1, -1, -1],
            "B1u": [1, 1, -1, -1, -1, -1, 1, 1],
            "B2u": [1, -1, 1, -1, -1, 1, -1, 1],
            "B3u": [1, -1, -1, 1, -1, 1, 1, -1],
        },
        "basis_functions": {
            "Ag": [],
            "B1g": ["Rz"],
            "B2g": ["Ry"],
            "B3g": ["Rx"],
            "Au": [],
            "B1u": ["z"],
            "B2u": ["y"],
            "B3u": ["x"],
        },
    }
