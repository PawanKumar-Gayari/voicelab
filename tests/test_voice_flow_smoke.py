from app.tools.symmetry import analyze_symmetry
from app.tools.representation import calculate_representation
from app.tools.verification import verify_representation


def _run_voice_flow(molecule: str):
    # Step 1: voice agent's symmetry-tool route
    symmetry = analyze_symmetry(molecule)

    assert symmetry["success"] is True
    data = symmetry["data"]

    assert data["molecule"].upper() == molecule.upper()
    assert isinstance(data["operations"], list)
    assert len(data["operations"]) > 0

    # Step 2: representation-tool route
    representation = calculate_representation(
        molecule=molecule,
        basis=["x", "y", "z"],
        operations=data["operations"],
    )

    assert representation["success"] is True
    rep_data = representation["data"]

    assert rep_data["representation_matrices"]
    assert rep_data["characters"]

    # Step 3: verification-tool route
    verification = verify_representation(
        molecule=molecule,
        operations=data["operations"],
        representation_matrices=rep_data["representation_matrices"],
        characters=rep_data["characters"],
    )

    assert verification["success"] is True
    assert verification["data"]["status"] == "PASS"


def test_voice_flow_smoke_bf3():
    _run_voice_flow("BF3")


def test_voice_flow_smoke_h2o():
    _run_voice_flow("H2O")