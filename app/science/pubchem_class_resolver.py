"""Phase 4: map verified raw symmetry operations to registered conjugacy classes.

This module is deliberately fail-closed. It only assigns a class when the
geometric signature is sufficient to distinguish the class. Existing local
molecule definitions are never modified.
"""
from __future__ import annotations
from typing import Any
import numpy as np

from app.science.pubchem_operation_classifier import classify_matrix

TOL=1e-6

def _vec(value):
    if value is None: return None
    v=np.asarray(value,dtype=float)
    n=np.linalg.norm(v)
    return v/n if n>TOL else None

def _same_axis(a,b):
    a,b=_vec(a),_vec(b)
    return a is not None and b is not None and abs(abs(float(np.dot(a,b)))-1)<1e-5

def _classify_d3h(items):
    # D3h: class membership follows operation type/order and, for reflections,
    # whether the plane contains the principal C3 axis.
    rotations=[x for x in items if x["classification"]["type"]=="rotation"]
    refs=[x for x in items if x["classification"]["type"]=="reflection"]
    impropers=[x for x in items if x["classification"]["type"]=="improper_rotation"]
    axis=None
    c3=[x for x in rotations if x["classification"].get("order")==3]
    if len(c3)==2:
        axis=c3[0]["classification"].get("axis")
    labels={}
    for x in items:
        c=x["classification"]; typ=c["type"]; oid=x["id"]
        if typ=="identity": labels[oid]="E"
        elif typ=="rotation" and c.get("order")==3: labels[oid]="2C3"
        elif typ=="rotation" and c.get("order")==2: labels[oid]="3C2'"
        elif typ=="reflection":
            normal=c.get("plane_normal")
            labels[oid]="sigma_h" if _same_axis(normal,axis) else "3sigma_v"
        elif typ=="improper_rotation" and c.get("order")==3: labels[oid]="2S3"
    return labels

def _classify_c3v(items):
    labels={}
    for x in items:
        c=x["classification"]; typ=c["type"]; oid=x["id"]
        if typ=="identity": labels[oid]="E"
        elif typ=="rotation" and c.get("order")==3: labels[oid]="2C3"
        elif typ=="reflection": labels[oid]="3sigma_v"
    return labels

def _classify_c2v(items):
    # C2v has two distinct vertical reflection classes in the
    # registry coordinate convention. For externally fetched planar
    # geometries, the molecular-plane reflection is mapped to the
    # registry's yz plane; the complementary vertical reflection is
    # mapped to xz.
    labels = {}

    for x in items:
        c = x["classification"]
        typ = c["type"]
        oid = x["id"]

        if typ == "identity":
            labels[oid] = "E"

        elif typ == "rotation" and c.get("order") == 2:
            labels[oid] = "C2"

        elif typ == "reflection":
            if x.get("planar_geometry") and x.get(
                "molecular_plane_branch"
            ):
                labels[oid] = "sigma_v(yz)"
            elif x.get("planar_geometry"):
                labels[oid] = "sigma_v(xz)"
            else:
                raise ValueError(
                    "C2v reflection lacks planar-geometry metadata."
                )

    return labels

def _classify_td(items):
    labels={}
    for x in items:
        c=x["classification"]; typ=c["type"]; oid=x["id"]
        if typ=="identity": labels[oid]="E"
        elif typ=="rotation" and c.get("order")==3: labels[oid]="8C3"
        elif typ=="rotation" and c.get("order")==2: labels[oid]="3C2"
        elif typ=="improper_rotation" and c.get("order")==4: labels[oid]="6S4"
        elif typ=="reflection": labels[oid]="6sigma_d"
    return labels

def _classify_simple(items):
    labels={}
    for x in items:
        c=x["classification"]; typ=c["type"]; oid=x["id"]
        if typ=="identity": labels[oid]="E"
        elif typ=="inversion": labels[oid]="i"
        elif typ=="rotation" and c.get("order")==2: labels[oid]="C2"
        elif typ=="reflection": labels[oid]="sigma_h"
    return labels

def assign_conjugacy_classes(operations:list[dict[str,Any]], point_group:Any)->dict[str,str]:
    """Return operation_id -> exact registry class, or raise ValueError."""
    items=[]
    for op in operations:
        if not op.get("verified"):
            raise ValueError(f"Operation {op.get('id')} is not verified.")
        matrix=op.get("matrix")
        if matrix is None:
            raise ValueError(f"Operation {op.get('id')} has no verified matrix.")
        c=op.get("classification") or classify_matrix(matrix)
        items.append({**op,"classification":c})

    # Point-group registry entries are dictionaries in the current
    # runtime. Keep compatibility with object-style callers as well.
    if isinstance(point_group, dict):
        pg = point_group["id"]
        expected = dict(point_group["class_sizes"])
    else:
        pg = point_group.point_group_id
        expected = dict(point_group.class_sizes)

    if pg=="D3h": labels=_classify_d3h(items)
    elif pg=="C3v": labels=_classify_c3v(items)
    elif pg=="C2v": labels=_classify_c2v(items)
    elif pg=="Td": labels=_classify_td(items)
    elif pg in {"C1","C2","Cs","Ci","C2h"}: labels=_classify_simple(items)
    else:
        raise ValueError(f"Phase 4 class resolver does not safely support {pg} yet.")

    if len(labels)!=len(items):
        missing=[x["id"] for x in items if x["id"] not in labels]
        raise ValueError(f"Could not classify operation(s): {', '.join(missing)}")

    counts={}
    for label in labels.values(): counts[label]=counts.get(label,0)+1
    if counts != expected:
        raise ValueError(
            f"Operation-class signature {counts} does not match registered "
            f"{pg} signature {expected}."
        )
    return labels
