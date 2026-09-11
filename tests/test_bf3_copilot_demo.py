from app.tools.operation_test import run_molecule_operation
from app.tools.symmetry import analyze_symmetry
from app.tools.full_analysis import analyze_molecule


def test_bf3_geometry_drives_d3h_inference():
    result = analyze_symmetry("BF3")
    assert result["success"] is True
    assert result["data"]["point_group"] == "D3h"
    assert result["data"]["verification"]["status"] == "PASS"
    assert result["data"]["verification"]["verified_operation_count"] == 12


def test_bf3_c4_is_actually_tested_and_fails():
    result = run_molecule_operation(
        "BF3",
        {"id": "C4_test", "symbol": "C4", "type": "rotation", "axis": [0, 0, 1], "angle_deg": 90},
    )
    assert result["success"] is True
    assert result["data"]["is_symmetry"] is False
    assert any(item["match"] is None for item in result["data"]["mapping"])


def test_full_analysis_uses_verified_point_group():
    result = analyze_molecule("BF3")
    assert result["success"] is True
    assert result["data"]["point_group"] == "D3h"
    assert result["data"]["symmetry_verification"]["status"] == "PASS"


def test_bf3_expected_positive_operations_are_verified():
    result = analyze_symmetry("BF3")
    ops = result["data"]["operations"]
    assert len(ops) == 12
    assert all(op["verified"] for op in ops)
    assert [op["id"] for op in ops] == ["E", "C3_1", "C3_2", "C2p_1", "C2p_2", "C2p_3", "sigma_h", "S3_1", "S3_2", "sigma_v_1", "sigma_v_2", "sigma_v_3"]
