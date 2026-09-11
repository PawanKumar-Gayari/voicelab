"""NH3 molecule definition for the automatic Molecule Registry."""

MOLECULE_ID = "NH3"

# Trigonal-pyramidal NH3 geometry.
# N is at the origin and the C3 axis is the +z axis.
NH3_COORDINATES = {
    "N": [0.0, 0.0, 0.0],
    "H1": [0.9448, 0.0, 0.3630],
    "H2": [-0.4724, 0.8182208014955377, 0.3630],
    "H3": [-0.4724, -0.8182208014955377, 0.3630],
}

NH3_BONDS = [
    {"a": 0, "b": 1, "order": 1},
    {"a": 0, "b": 2, "order": 1},
    {"a": 0, "b": 3, "order": 1},
]

NH3_OPERATIONS = [
    {
        "id": "E",
        "symbol": "E",
        "type": "identity",
        "class": "E",
    },
    {
        "id": "C3_z",
        "symbol": "C3(z)",
        "type": "rotation",
        "axis": [0.0, 0.0, 1.0],
        "angle_deg": 120.0,
        "class": "C3",
    },
    {
        "id": "C3_2_z",
        "symbol": "C3^2(z)",
        "type": "rotation",
        "axis": [0.0, 0.0, 1.0],
        "angle_deg": 240.0,
        "class": "C3",
    },
    {
        "id": "sigma_v_xz",
        "symbol": "sigma_v(xz)",
        "type": "reflection",
        "plane_normal": [0.0, 1.0, 0.0],
        "class": "sigma_v",
    },
    {
        "id": "sigma_v_60",
        "symbol": "sigma_v(60deg)",
        "type": "reflection",
        "plane_normal": [-0.8660254038, 0.5, 0.0],
        "class": "sigma_v",
    },
    {
        "id": "sigma_v_120",
        "symbol": "sigma_v(120deg)",
        "type": "reflection",
        "plane_normal": [-0.8660254038, -0.5, 0.0],
        "class": "sigma_v",
    },
]


def get_molecule_data() -> dict:
    """Return NH3 data using the registry-standard interface."""
    return {
        "id": MOLECULE_ID,
        "name": "NH3",
        "formula": "NH3",
        "point_group": "C3v",
        "coordinates": {
            atom: coordinates.copy()
            for atom, coordinates in NH3_COORDINATES.items()
        },
        "bonds": [
            bond.copy()
            for bond in NH3_BONDS
        ],
        "operations": [
            operation.copy()
            for operation in NH3_OPERATIONS
        ],
        "matrices": {},
    }
