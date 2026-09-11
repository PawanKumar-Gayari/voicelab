"""C2v point group character-table data for the Point Group Registry.

Class ordering and operation IDs are chosen to line up exactly with the
existing H2O molecule definition in app.science.molecules.h2o:

    E, C2, sigma_v(xz), sigma_v(yz)
"""

POINT_GROUP_ID = "C2v"


def get_point_group_data() -> dict:
    """Return C2v character-table data using the registry-standard interface."""
    return {
        "id": POINT_GROUP_ID,
        "order": 4,
        "classes": ["E", "C2", "sigma_v(xz)", "sigma_v(yz)"],
        "class_sizes": {
            "E": 1,
            "C2": 1,
            "sigma_v(xz)": 1,
            "sigma_v(yz)": 1,
        },
        "irreps": ["A1", "A2", "B1", "B2"],
        "irrep_dimensions": {"A1": 1, "A2": 1, "B1": 1, "B2": 1},
        "character_table": {
            "A1": [1, 1, 1, 1],
            "A2": [1, 1, -1, -1],
            "B1": [1, -1, 1, -1],
            "B2": [1, -1, -1, 1],
        },
        "basis_functions": {
            "A1": ["z"],
            "A2": ["Rz"],
            "B1": ["x", "Ry"],
            "B2": ["y", "Rx"],
        },
    }
