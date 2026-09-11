#!/usr/bin/env python3

from pathlib import Path
import shutil
import re
from datetime import datetime

ROOT = Path("/home/aspirantveda-voicelab/htdocs/Voicelab")
SCI = ROOT / "app" / "science"
RUNTIME = SCI / "pubchem_runtime.py"
SOLVER = SCI / "pubchem_permutation_solver.py"

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / f".ch4_td_fix_backup_{stamp}"
BACKUP.mkdir()

shutil.copy2(RUNTIME, BACKUP / "pubchem_runtime.py")

solver = r'''
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

    symmetric = (
        matrix + matrix.T
    ) / 2.0

    _, vectors = np.linalg.eigh(
        symmetric
    )

    axis = vectors[:, -1]
    norm = np.linalg.norm(axis)

    if norm < 1e-10:
        return None

    axis /= norm

    sigma_h = (
        np.eye(3)
        - 2.0 * np.outer(axis, axis)
    )

    rotation = sigma_h @ matrix

    cosine = (
        float(np.trace(rotation)) - 1.0
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

        if any(
            _same_matrix(matrix, old)
            for old in seen
        ):
            continue

        operation = _operation_from_matrix(
            matrix,
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

        operation["matrix"] = matrix.tolist()
        operation["rms_residual"] = rms

        seen.append(matrix)
        operations.append(operation)

    return operations
'''

SOLVER.write_text(
    solver,
    encoding="utf-8",
)

text = RUNTIME.read_text(
    encoding="utf-8"
)

import_line = (
    "from app.science.pubchem_permutation_solver "
    "import discover_verified_operations"
)

if import_line not in text:
    lines = text.splitlines()

    insert_at = 0

    for index, line in enumerate(lines):
        if line.startswith(("import ", "from ")):
            insert_at = index + 1

    lines.insert(
        insert_at,
        import_line,
    )

    text = "\n".join(lines) + "\n"

pattern = re.compile(
    r"(?ms)^def verified_external_operations\(.*?(?=^def |\Z)"
)

match = pattern.search(text)

if not match:
    raise RuntimeError(
        "verified_external_operations() "
        "was not found in pubchem_runtime.py"
    )

replacement = (
    "def verified_external_operations("
    "atoms, tolerance=1e-4"
    "):\n"
    "    return discover_verified_operations("
    "atoms, tolerance=tolerance"
    ")\n\n"
)

text = (
    text[:match.start()]
    + replacement
    + text[match.end():]
)

RUNTIME.write_text(
    text,
    encoding="utf-8",
)

print("PATCH FILES WRITTEN")
print("Solver:", SOLVER)
print("Runtime:", RUNTIME)
print("Backup:", BACKUP)
