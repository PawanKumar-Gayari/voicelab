"""H2O molecule definition for the automatic Molecule Registry."""

MOLECULE_ID = "H2O"

H2O_COORDINATES = {
    "O": [0.0, 0.0, 0.0],
    "H1": [0.0, 0.757, 0.587],
    "H2": [0.0, -0.757, 0.587],
}

# Operation fields intentionally match app.science.transformations exactly:
# rotation/improper_rotation -> axis + angle_deg
# reflection -> plane_normal
H2O_BONDS = [
    {"a": 0, "b": 1, "order": 1},
    {"a": 0, "b": 2, "order": 1},
]

H2O_OPERATIONS = [
    {
        "id": "E",
        "symbol": "E",
        "type": "identity",
        "class": "E",
    },
    {
        "id": "C2",
        "symbol": "C2(z)",
        "type": "rotation",
        "axis": [0.0, 0.0, 1.0],
        "angle_deg": 180.0,
        "class": "C2",
    },
    {
        "id": "sigma_v_xz",
        "symbol": "sigma_v(xz)",
        "type": "reflection",
        "plane_normal": [0.0, 1.0, 0.0],
        "class": "sigma_v(xz)",
    },
    {
        "id": "sigma_v_yz",
        "symbol": "sigma_v(yz)",
        "type": "reflection",
        "plane_normal": [1.0, 0.0, 0.0],
        "class": "sigma_v(yz)",
    },
]


def get_molecule_data() -> dict:
    """Return H2O data using the registry-standard interface."""
    return {
        "id": MOLECULE_ID,
        "name": "H2O",
        "formula": "H2O",
        "point_group": "C2v",
        "coordinates": {
            atom: coordinates.copy()
            for atom, coordinates in H2O_COORDINATES.items()
        },
        "bonds": [
            bond.copy()
            for bond in H2O_BONDS
        ],
        "operations": [
            operation.copy()
            for operation in H2O_OPERATIONS
        ],
        "matrices": {},
    }
