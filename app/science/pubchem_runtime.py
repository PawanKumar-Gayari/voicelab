"""Runtime scientific boundary for validated external PubChem geometries."""
from __future__ import annotations
from typing import Any
from collections import Counter
import numpy as np

from app.science.geometry_symmetry import check_operation
from app.science.molecule_registry import MoleculeDefinition
from app.science.point_group_registry import get_point_group
from app.science.pubchem_class_resolver import assign_conjugacy_classes
from app.science.pubchem_operation_classifier import classify_matrix
from app.science.pubchem_principal_axes import generate_principal_axis_candidates
from app.science.geometry_normalizer import normalize_atoms
from app.science.pubchem_client import fetch_3d
from app.science.reduction import reduce_representation, format_reduction_summary
from app.science.pubchem_linear import is_linear_triatomic, analyze_co2_runtime
from app.science.pubchem_permutation_solver import discover_verified_operations
from app.tools.vibrational_analysis import calculate_vibrational_analysis


def runtime_definition(molecule_id: str, name: str, formula: str,
                       atoms: list[dict[str, Any]], operations: list[dict[str, Any]],
                       point_group: str) -> MoleculeDefinition:
    """Create the exact current-server MoleculeDefinition shape in memory."""
    pg = get_point_group(point_group)
    labels = assign_conjugacy_classes(operations, pg)
    normalized = []
    matrices = {}
    for op in operations:
        item = dict(op)
        item["class"] = labels[item["id"]]
        normalized.append(item)
        matrices[item["id"]] = item["matrix"]
    coordinates = {
        a["label"]: list(map(float, a["coord"])) for a in atoms
    }
    return MoleculeDefinition(
        molecule_id=molecule_id.upper(),
        name=name,
        formula=formula,
        point_group=pg.point_group_id,
        coordinates=coordinates,
        operations=normalized,
        matrices=matrices,
        bonds=[],
    )


def verified_external_operations(atoms, tolerance=1e-4):
    """Discover externally sourced symmetry operations using bounded tolerance.

    PubChem coordinates may be rounded.  A tolerance is accepted only when
    the resulting operations form a complete registered finite point group.
    Incomplete operation sets are never returned.
    """
    tolerances = [tolerance]

    for candidate in (1e-3, 3e-3, 1e-2):
        if candidate > tolerance and candidate not in tolerances:
            tolerances.append(candidate)

    supported_groups = ("C1", "C2", "Cs", "Ci", "C2h", "C2v", "C3v", "D3h", "Td")
    c1_fallback = None

    for current_tolerance in tolerances:
        operations = discover_verified_operations(
            atoms,
            tolerance=current_tolerance,
        )

        if not operations:
            continue

        for operation in operations:
            operation["verified"] = True

        matches = []

        for pgid in supported_groups:
            pg = get_point_group(pgid)

            try:
                labels = assign_conjugacy_classes(operations, pg)
            except (ValueError, TypeError):
                continue

            actual_counts = Counter(labels.values())
            expected_counts = dict(pg.class_sizes)

            if dict(actual_counts) == expected_counts:
                matches.append((pgid, labels))

        if len(matches) == 1:
            pgid, labels = matches[0]

            if pgid == "C1":
                c1_fallback = (operations, labels)
                continue

            for operation in operations:
                operation["class"] = labels[operation["id"]]
                operation["_verification_tolerance"] = current_tolerance

            return operations

        if len(matches) > 1:
            raise ValueError(
                "External geometry resolves to multiple supported "
                "finite point groups at the same tolerance."
            )

    if c1_fallback is not None:
        operations, labels = c1_fallback

        for operation in operations:
            operation["class"] = labels[operation["id"]]

        return operations

    raise ValueError(
        "External geometry could not be resolved to one complete "
        "supported finite point group within the numerical tolerance range."
    )

def _atom_permutation(atoms: list[dict[str, Any]], op: dict[str, Any], tolerance: float = 1e-4) -> list[int]:
    """Normalize matcher mappings into source-index -> target-index."""
    result = check_operation(atoms, op, tolerance=tolerance)
    if not result.get("is_symmetry"):
        raise ValueError(f"Operation {op.get('id')} is not geometrically verified.")

    mapping = result.get("mapping") or []

    # Some matcher implementations may already return a direct integer
    # permutation.
    if len(mapping) == len(atoms) and all(isinstance(x, int) for x in mapping):
        return list(mapping)

    # The authoritative geometry matcher returns atom labels:
    # {"from": source_label, "match": target_label, ...}.
    label_to_index = {}

    for index, atom in enumerate(atoms):
        # The geometry matcher normalizes list input to positional labels
        # ("0", "1", ...), while runtime atoms may carry semantic labels
        # such as "C1", "H2", etc. Accept both representations.
        label_to_index[str(index)] = index
        label_to_index[str(atom["label"])] = index

    perm = [-1] * len(atoms)

    for entry in mapping:
        if not isinstance(entry, dict):
            continue

        src = entry.get(
            "source",
            entry.get("from", entry.get("source_index")),
        )
        dst = entry.get(
            "target",
            entry.get("match", entry.get("to", entry.get("target_index"))),
        )

        if isinstance(src, int) and isinstance(dst, int):
            if 0 <= src < len(atoms) and 0 <= dst < len(atoms):
                perm[src] = dst
            continue

        if src is not None and dst is not None:
            src_index = label_to_index.get(str(src))
            dst_index = label_to_index.get(str(dst))

            if src_index is not None and dst_index is not None:
                perm[src_index] = dst_index

    if any(index < 0 for index in perm):
        raise ValueError(
            "VoiceLab geometry matcher returned an incomplete atom permutation."
        )

    if len(set(perm)) != len(atoms):
        raise ValueError(
            "VoiceLab geometry matcher returned a non-bijective atom permutation."
        )

    return perm

def calculate_3n_runtime(atoms: list[dict[str, Any]], operations: list[dict[str, Any]], tolerance: float = 1e-4) -> dict[str, Any]:
    """Construct the exact 3N displacement representation D^(3N)(g)."""
    n = len(atoms)
    matrices, chars, permutations = {}, {}, {}
    for op in operations:
        m = np.asarray(op["matrix"], dtype=float)
        if m.shape != (3, 3):
            raise ValueError("Operation matrix must be 3x3.")
        perm = _atom_permutation(atoms, op, tolerance=tolerance)
        d = np.zeros((3*n, 3*n), dtype=float)
        for src, dst in enumerate(perm):
            d[3*dst:3*dst+3, 3*src:3*src+3] = m
        matrices[op["id"]] = d.tolist()
        chars[op["id"]] = float(np.trace(d))
        permutations[op["id"]] = perm
    return {"dimension": 3*n, "representation_matrices": matrices,
            "characters": chars, "atom_permutations": permutations}


def analyze_external_finite(
    identifier: str,
    basis: list[str] | None = None,
    include_vibrations: bool = False,
) -> dict[str, Any]:
    """Analyze a non-linear external molecule only if its finite group is uniquely supported."""
    record = fetch_3d(identifier)
    atoms = normalize_atoms(record.atoms)
    if is_linear_triatomic(atoms):
        raise ValueError("Linear external molecule requires the explicit linear-group boundary.")
    operations = verified_external_operations(atoms)
    # A finite group is accepted only through the existing class resolver.
    matches = []
    for pgid in ("C1", "C2", "Cs", "Ci", "C2h", "C2v", "C3v", "D3h", "Td"):
        pg = get_point_group(pgid)
        try:
            labels = assign_conjugacy_classes(operations, pg)
        except Exception:
            continue
        label_counts = Counter(labels.values())
        expected_counts = dict(pg.class_sizes)

        if dict(label_counts) == expected_counts:
            matches.append((pgid, labels))
    if len(matches) != 1:
        raise ValueError("External geometry did not resolve to one supported finite point group.")
    pgid, labels = matches[0]
    pg = get_point_group(pgid)
    for op in operations:
        op["class"] = labels[op["id"]]
    verification_tolerances = {
        float(op.get("_verification_tolerance", 1e-4))
        for op in operations
    }

    if len(verification_tolerances) != 1:
        raise ValueError(
            "External operations do not share one verification tolerance."
        )

    verification_tolerance = verification_tolerances.pop()
    rep = calculate_3n_runtime(
        atoms,
        operations,
        tolerance=verification_tolerance,
    )
    class_chars = {}
    for cls in pg.classes:
        vals = [rep["characters"][o["id"]] for o in operations if o["class"] == cls]
        if not vals:
            raise ValueError(f"Missing verified operation class {cls}.")
        if max(vals) - min(vals) > 1e-6:
            raise ValueError(f"Characters are not constant within class {cls}.")
        class_chars[cls] = vals[0]
    gamma = [class_chars[c] for c in pg.classes]
    reduction = reduce_representation(gamma, pg)
    reduction["summary"] = format_reduction_summary(reduction)

    # Expose the same authoritative reduction summary through the
    # representation payload consumed by the workspace/API.
    rep["reduction"] = reduction["summary"]

    vibrational_analysis = None

    if include_vibrations:
        definition = runtime_definition(
            molecule_id=f"PUBCHEM-{record.cid}",
            name=record.name,
            formula=record.formula,
            atoms=atoms,
            operations=operations,
            point_group=pgid,
        )

        vibrational_result = calculate_vibrational_analysis(definition)

        if not vibrational_result.get("success"):
            raise ValueError(
                f"External vibrational analysis failed: "
                f"{vibrational_result.get('error')}"
            )

        vibrational_analysis = vibrational_result.get("data")

    return {
        "molecule": {"id": f"PUBCHEM-{record.cid}", "name": record.name,
                     "formula": record.formula, "point_group": pgid,
                     "coordinates": {a["label"]: a["coord"] for a in atoms}},
        "point_group": pgid,
        "basis": basis or ["x", "y", "z"],
        "operations": operations,
        "representation": rep,
        "group_theory": {"classes": pg.classes, "character_table": pg.character_table,
                          "irreps": pg.irreps, "irrep_dimensions": pg.irrep_dimensions,
                          "operation_to_class": {o["id"]: o["class"] for o in operations},
                          "reducible_characters": gamma, "reduction": reduction},
        "verification": {"status": "PASS", "source": "PubChem",
                          "verified_operation_count": len(operations)},
        "source": {"provider": "PubChem", "cid": record.cid},
        "vibrational_analysis": vibrational_analysis,
    }
