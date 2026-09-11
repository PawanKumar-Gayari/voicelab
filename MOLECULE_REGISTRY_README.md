# VoiceLab Molecule Registry & Point Group Registry

## Purpose

Automatically discover molecule definitions **and** point-group character
tables, so dropping in a new molecule file is enough for the full pipeline
(symmetry → representation → reduction into irreducible representations →
verification) to work for it — no code changes elsewhere.

## Add a new molecule

Create:

```text
app/science/molecules/<molecule>.py
```

and expose:

```python
MOLECULE_ID = "CH4"

def get_molecule_data() -> dict:
    return {
        "id": "CH4",
        "name": "CH4",
        "formula": "CH4",
        "point_group": "Td",
        "coordinates": ...,
        "operations": [...],
        "matrices": {...},
    }
```

No edit is required in `molecule_registry.py`.

### Operations need a `"class"` field

Each entry in `operations` should include a `"class"` key naming the
conjugacy class it belongs to, using the exact class label from the
molecule's point group (see below). Example, for an H2O-style operation:

```python
{
    "id": "C2",
    "symbol": "C2(z)",
    "type": "rotation",
    "axis": [0.0, 0.0, 1.0],
    "angle_deg": 180.0,
    "class": "C2",
}
```

This is the only per-molecule information `app/tools/full_analysis.py`
needs to group operations into classes — it never branches on the
molecule's identity.

## Add a new point group

If the molecule's point group isn't already registered (see current list
below), create:

```text
app/science/point_groups/<point_group>.py
```

and expose:

```python
POINT_GROUP_ID = "Td"

def get_point_group_data() -> dict:
    return {
        "id": "Td",
        "order": 24,
        "classes": ["E", "8C3", "3C2", "6S4", "6sigma_d"],
        "class_sizes": {"E": 1, "8C3": 8, "3C2": 3, "6S4": 6, "6sigma_d": 6},
        "irreps": ["A1", "A2", "E", "T1", "T2"],
        "irrep_dimensions": {"A1": 1, "A2": 1, "E": 2, "T1": 3, "T2": 3},
        "character_table": {
            "A1": [1, 1, 1, 1, 1],
            "A2": [1, 1, 1, -1, -1],
            "E":  [2, -1, 2, 0, 0],
            "T1": [3, 0, -1, 1, -1],
            "T2": [3, 0, -1, -1, 1],
        },
        "basis_functions": {  # optional, for reporting only
            "T2": ["(x, y, z)"],
        },
    }
```

No edit is required in `point_group_registry.py`. The registry validates
that class sizes sum to the declared order and that the sum of squared
irrep dimensions equals the order, so a typo is caught immediately (as a
discovery error, not a silent wrong answer) instead of crashing the app.

No edit is required in `app/science/reduction.py` either — the reduction
formula is entirely generic over whatever `PointGroupDefinition` it's
given.

## Current registration

| Molecules | Point groups already registered |
|---|---|
| BF3, H2O | C1, Cs, Ci, C2, C2v, C3v, C2h, D2h, D3h, Td |

BF3 is registered through `app/science/molecules/bf3.py`, an adapter that
reuses the existing `app.science.bf3` implementation and only attaches
`"class"` labels on top — the working BF3 mathematics and voice pipeline
are untouched.

## The `full_analysis` tool

`app/tools/full_analysis.py::analyze_molecule(molecule, basis)` is the
registry-driven, one-call replacement for `app/tools/bf3_analysis.py`
(which remains, untouched, as the BF3/D3h-specific implementation it
always was). It is wired into the voice agent
(`app/voice/assemblyai_agent.py`) as the `full_analysis` tool, and its
result is synchronized into session state via a new `full_analysis`
branch in `app/voice/session.py` and `ResearchSession.update_reduction()`
in `app/agent/state.py`. The HTML report
(`app/report/generator.py`) renders the character table and Γ
decomposition when this data is present.

## Important

Adding this did not require touching, and did not change the behavior
of:

- `app/science/bf3.py`
- `app/science/d3h.py`
- `app/tools/bf3_analysis.py`
- `analyze_symmetry`, `calculate_representation`, `verify_representation`
  (still work exactly as before, individually)

`full_analysis` is additive: it is a new tool alongside the existing
three, not a replacement for them.

## Test

From the project root:

```bash
pytest tests/test_molecule_registry.py tests/test_point_group_registry.py \
       tests/test_reduction.py tests/test_full_analysis.py \
       tests/test_full_analysis_voice_wiring.py -v
```

Expected: all tests pass. The full suite (`pytest tests/ -q`) should show
80 passed.
