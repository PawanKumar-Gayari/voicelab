
from __future__ import annotations

import itertools
from typing import Any

import numpy as np

from app.science.geometry_symmetry import check_operation
from app.science.pubchem_operation_classifier import classify_matrix

DEFAULT_TOLERANCE = 1e-4
MATRIX_TOLERANCE = 1e-7
MAX_PERMUTATION_ATOMS = 10


def _center(coords):
    return coords - np.mean(coords, axis=0, keepdims=True)


def _procrustes(source, target):
    u, _, vt = np.linalg.svd(source.T @ target)
    matrix = u @ vt
    residual = np.linalg.norm(source @ matrix - target, axis=1)
    rms = float(np.sqrt(np.mean(residual ** 2)))
    return matrix, rms


def _same_matrix(a, b):
    return bool(
        np.allclose(
            a,
            b,
            atol=MATRIX_TOLERANCE,
            rtol=0.0,
        )
    )


def _rotation_axis(matrix):
    values, vectors = np.linalg.eig(matrix)
    indices = np.where(
        np.abs(values.real - 1.0) < 1e-5
    )[0]

    if len(indices) == 0:
        return None

    axis = np.real(vectors[:, indices[0]])
    norm = np.linalg.norm(axis)

    if norm < 1e-10:
        return None

    return axis / norm


def _operation_from_matrix(matrix, index):
    classify_matrix(matrix)

    determinant = float(np.linalg.det(matrix))

    if np.allclose(
        matrix,
        np.eye(3),
        atol=1e-6,
        rtol=0.0,
    ):
        return {
            "id": f"EXT-E-{index}",
            "type": "identity",
        }

    if determinant > 0:
        axis = _rotation_axis(matrix)

        if axis is None:
            return None

        cosine = (
            float(np.trace(matrix)) - 1.0
        ) / 2.0

        cosine = max(-1.0, min(1.0, cosine))

        angle = float(
            np.degrees(
                np.arccos(cosine)
            )
        )

        return {
            "id": f"EXT-R-{index}",
            "type": "rotation",
            "axis": axis.tolist(),
            "angle_deg": angle,
        }

    if abs(float(np.trace(matrix)) - 1.0) < 1e-5:
        values, vectors = np.linalg.eig(matrix)

        indices = np.where(
            np.abs(values.real + 1.0) < 1e-5
        )[0]

        if len(indices) == 0:
            return None

        normal = np.real(
            vectors[:, indices[0]]
        )

        norm = np.linalg.norm(normal)

        if norm < 1e-10:
            return None

        normal /= norm

        return {
            "id": f"EXT-SIGMA-{index}",
            "type": "reflection",
            "plane_normal": normal.tolist(),
        }

    # For an improper rotation, VoiceLab's matrix classifier
    # defines the associated proper rotation as -M.
    # Recover the same axis/angle convention so the existing
    # transformation engine reconstructs the exact S_n operation.
    proper = -matrix

    axis = _rotation_axis(proper)
    if axis is None:
        return None

    cosine = (
        float(np.trace(proper)) - 1.0
    ) / 2.0

    cosine = max(-1.0, min(1.0, cosine))

    angle = float(
        np.degrees(
            np.arccos(cosine)
        )
    )

    return {
        "id": f"EXT-S-{index}",
        "type": "improper_rotation",
        "axis": axis.tolist(),
        "angle_deg": angle,
    }


def discover_verified_operations(
    atoms: list[dict[str, Any]],
    tolerance: float = DEFAULT_TOLERANCE,
):
    atom_count = len(atoms)

    if atom_count > MAX_PERMUTATION_ATOMS:
        raise ValueError(
            "External permutation symmetry discovery "
            f"is limited to {MAX_PERMUTATION_ATOMS} atoms; "
            f"received {atom_count}."
        )

    elements = [
        str(atom["element"])
        .strip()
        .upper()
        for atom in atoms
    ]

    coordinates = np.asarray(
        [atom["coord"] for atom in atoms],
        dtype=float,
    )

    centered = _center(coordinates)

    groups = {}

    for index, element in enumerate(elements):
        groups.setdefault(
            element,
            [],
        ).append(index)

    permutation_groups = [
        list(itertools.permutations(indices))
        for indices in groups.values()
    ]

    seen = []
    operations = []

    for permutation_product in itertools.product(
        *permutation_groups
    ):
        target = centered.copy()

        for indices, permutation in zip(
            groups.values(),
            permutation_product,
        ):
            for source_index, destination_index in zip(
                indices,
                permutation,
            ):
                target[destination_index] = (
                    centered[source_index]
                )

        matrix, rms = _procrustes(
            centered,
            target,
        )

        if rms > tolerance:
            continue

        if not np.allclose(
            matrix.T @ matrix,
            np.eye(3),
            atol=1e-6,
            rtol=0.0,
        ):
            continue

        # For rank-2 molecular geometries, the coordinates are planar.
        # SVD/Procrustes has two equally valid orthogonal branches because
        # reflection through the molecular plane leaves every centered
        # coordinate unchanged.  Generate the complementary branch
        # generically rather than hard-coding any molecule.
        singular_values = np.linalg.svd(
            centered,
            compute_uv=False,
        )

        rank_scale = max(
            float(singular_values[0]),
            1.0,
        )

        planar = (
            len(singular_values) == 3
            and singular_values[1] > 1e-10 * rank_scale
            and singular_values[2] <= 1e-8 * rank_scale
        )

        candidate_matrices = [(matrix, False)]

        if planar:
            _, _, vh = np.linalg.svd(centered)
            normal = vh[-1]
            normal_norm = float(np.linalg.norm(normal))

            if normal_norm > 1e-12:
                normal = normal / normal_norm
                plane_reflection = (
                    np.eye(3)
                    - 2.0 * np.outer(normal, normal)
                )

                alternate = plane_reflection @ matrix

                if not any(
                    _same_matrix(alternate, candidate)
                    for candidate, _ in candidate_matrices
                ):
                    candidate_matrices.append(
                        (alternate, True)
                    )

        for candidate_matrix, used_planar_branch in candidate_matrices:
            candidate_residual = float(
                np.sqrt(
                    np.mean(
                        np.linalg.norm(
                            centered @ candidate_matrix - target,
                            axis=1,
                        ) ** 2
                    )
                )
            )

            if candidate_residual > tolerance:
                continue

            if not np.allclose(
                candidate_matrix.T @ candidate_matrix,
                np.eye(3),
                atol=1e-6,
                rtol=0.0,
            ):
                continue

            if any(
                _same_matrix(candidate_matrix, old)
                for old in seen
            ):
                continue

            operation = _operation_from_matrix(
                candidate_matrix,
                len(operations),
            )

            if operation is None:
                continue

            verification = check_operation(
                atoms,
                operation,
                tolerance=tolerance,
            )

            if not verification.get("success"):
                continue

            if not verification.get("is_symmetry"):
                continue

            operation["matrix"] = candidate_matrix.tolist()
            operation["rms_residual"] = candidate_residual

            if planar:
                operation["planar_geometry"] = True
                operation["molecular_plane_branch"] = not used_planar_branch

            seen.append(candidate_matrix)
            operations.append(operation)

    return operations
