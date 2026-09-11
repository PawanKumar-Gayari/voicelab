import numpy as np

from app.science.molecules.h2o import H2O_COORDINATES, H2O_OPERATIONS
from app.science.transformations import build_transformation_matrix


TOLERANCE = 1e-10


EXPECTED_MAPPINGS = {
    "E": {
        "O": "O",
        "H1": "H1",
        "H2": "H2",
    },
    "C2": {
        "O": "O",
        "H1": "H2",
        "H2": "H1",
    },
    "sigma_v_xz": {
        "O": "O",
        "H1": "H2",
        "H2": "H1",
    },
    "sigma_v_yz": {
        "O": "O",
        "H1": "H1",
        "H2": "H2",
    },
}


def _apply_operation(matrix, coordinate):
    """Apply r' = M @ r."""
    return np.asarray(matrix, dtype=float) @ np.asarray(
        coordinate, dtype=float
    )


def _find_atom_mapping(transformed_coordinate):
    """Find which H2O atom occupies the transformed coordinate."""
    for atom, coordinate in H2O_COORDINATES.items():
        if np.allclose(
            transformed_coordinate,
            coordinate,
            atol=TOLERANCE,
            rtol=TOLERANCE,
        ):
            return atom

    return None


def test_h2o_all_symmetry_operations_and_atom_mappings():
    """Verify E, C2(z), sigma_v(xz), and sigma_v(yz)."""

    for operation in H2O_OPERATIONS:
        operation_id = operation["id"]

        result = build_transformation_matrix(operation)

        assert result["success"], (
            f"{operation_id} failed to build: "
            f"{result.get('error')}"
        )

        matrix = result["matrix"]

        expected_mapping = EXPECTED_MAPPINGS[operation_id]

        for atom, coordinate in H2O_COORDINATES.items():
            transformed = _apply_operation(matrix, coordinate)

            expected_atom = expected_mapping[atom]
            expected_coordinate = H2O_COORDINATES[expected_atom]

            # Verify the actual transformed Cartesian coordinate.
            assert np.allclose(
                transformed,
                expected_coordinate,
                atol=TOLERANCE,
                rtol=TOLERANCE,
            ), (
                f"{operation_id}: {atom} transformed to "
                f"{transformed}, expected {expected_coordinate}"
            )

            # Verify the corresponding atom mapping.
            actual_atom = _find_atom_mapping(transformed)

            assert actual_atom == expected_atom, (
                f"{operation_id}: {atom} -> {actual_atom}, "
                f"expected {expected_atom}"
            )


def test_h2o_expected_matrices():
    """Verify the exact Cartesian matrices for all four operations."""

    expected_matrices = {
        "E": [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "C2": [
            [-1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "sigma_v_xz": [
            [1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "sigma_v_yz": [
            [-1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
    }

    for operation in H2O_OPERATIONS:
        operation_id = operation["id"]

        result = build_transformation_matrix(operation)

        assert result["success"], (
            f"{operation_id} failed: {result.get('error')}"
        )

        assert np.allclose(
            result["matrix"],
            expected_matrices[operation_id],
            atol=TOLERANCE,
            rtol=TOLERANCE,
        ), (
            f"{operation_id} matrix is incorrect.\n"
            f"Actual:\n{np.asarray(result['matrix'])}\n"
            f"Expected:\n{np.asarray(expected_matrices[operation_id])}"
        )