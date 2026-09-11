"""Phase 4 external-geometry bridge into VoiceLab's existing deterministic pipeline.

The bridge creates an in-memory MoleculeDefinition and invokes the same
representation, reduction, verification and optional vibration functions used
by full_analysis.py. It does not register a module on disk and therefore cannot
alter BF3/H2O/NH3 registry behavior.
"""
from __future__ import annotations
from typing import Any
from app.science.molecule_registry import MoleculeDefinition
from app.science.point_group_registry import get_point_group
from app.science.pubchem_class_resolver import assign_conjugacy_classes
from app.tools.symmetry import analyze_symmetry
from app.tools.molecular_representation import calculate_3n_representation
from app.tools.verification import verify_representation
from app.tools.vibrational_analysis import calculate_vibrational_analysis
from app.science.reduction import reduce_representation, format_reduction_summary

def _success(data): return {"success":True,"tool":"pubchem_full_analysis","data":data,"error":None}
def _failure(code,msg): return {"success":False,"tool":"pubchem_full_analysis","data":None,"error":{"code":code,"message":msg}}

def build_runtime_definition(
    molecule_id:str,name:str,formula:str,coordinates:dict[str,list[float]],
    point_group:str,operations:list[dict[str,Any]]
)->MoleculeDefinition:
    pg=get_point_group(point_group)
    labels=assign_conjugacy_classes(operations,pg)
    normalized=[]
    matrices={}
    for op in operations:
        item=dict(op)
        item["class"]=labels[item["id"]]
        normalized.append(item)
        matrices[item["id"]]=item["matrix"]
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

def analyze_external_geometry(
    molecule_id:str,name:str,formula:str,coordinates:dict[str,list[float]],
    operations:list[dict[str,Any]], point_group:str,basis:list[str]|None=None,
    include_vibrations:bool=False,
):
    if basis is None: basis=["x","y","z"]
    try:
        definition=build_runtime_definition(molecule_id,name,formula,coordinates,point_group,operations)
        # Existing tools resolve molecule IDs through the disk registry, so we
        # cannot call analyze_symmetry directly with this transient definition.
        # Instead calculate/verify against the exact same operation schema here.
        verification_tolerances = {
            float(operation.get("_verification_tolerance", 1e-4))
            for operation in definition.operations
        }

        if len(verification_tolerances) != 1:
            raise ValueError(
                "External operations do not share one verification tolerance."
            )

        verification_tolerance = next(iter(verification_tolerances))

        rep = calculate_3n_representation(
            definition,
            operations=definition.operations,
            tolerance=verification_tolerance,
        )
        if not rep.get("success"): return _failure("REPRESENTATION_FAILED",str(rep.get("error")))
        data=rep.get("data") or {}
        characters=data.get("characters") or {}
        class_chars={}
        for op in definition.operations:
            class_chars.setdefault(op["class"],float(characters[op["id"]]))
        pg=get_point_group(point_group)
        gamma=[class_chars[c] for c in pg.classes]
        reduction=reduce_representation(gamma,pg)
        reduction["summary"]=format_reduction_summary(reduction)
        verification=verify_representation(
            molecule=definition,operations=definition.operations,
            representation_matrices=data.get("representation_matrices") or {},
            characters=characters,
        )
        if not verification.get("success"):
            return _failure("VERIFICATION_FAILED",str(verification.get("error")))

        vibrational_analysis = None
        if include_vibrations:
            vibrational_result = calculate_vibrational_analysis(definition)
            if not vibrational_result.get("success"):
                return _failure(
                    "VIBRATIONAL_ANALYSIS_FAILED",
                    str(vibrational_result.get("error")),
                )
            vibrational_analysis = vibrational_result.get("data")

        return _success({
            "molecule":{"id":definition.molecule_id,"name":name,"formula":formula,
                       "point_group":pg.point_group_id,"coordinates":coordinates},
            "point_group":pg.point_group_id,"operations":definition.operations,
            "basis":basis,"representation":data,
            "group_theory":{"classes":pg.classes,"character_table":pg.character_table,
                            "irreps":pg.irreps,"irrep_dimensions":pg.irrep_dimensions,
                            "operation_to_class":{o["id"]:o["class"] for o in definition.operations},
                            "reducible_characters":gamma,"reduction":reduction},
            "verification":verification.get("data",{}),
            "vibrational_analysis":vibrational_analysis,
        })
    except Exception as exc:
        return _failure("PUBCHEM_PIPELINE_ERROR",str(exc))
