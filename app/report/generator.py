"""
VoiceLab report generator.

Converts a completed research session into a simple, readable
scientific report.

This module:
    - reads research state,
    - formats scientific results,
    - clearly indicates verification status.

It does NOT:
    - perform scientific calculations,
    - call the AI agent,
    - call AssemblyAI,
    - calculate matrices or characters.
"""

from __future__ import annotations

from html import escape
from typing import Any


def _format_value(value: Any) -> str:
    """Convert a Python value into readable report text."""
    if isinstance(value, float):
        return f"{value:.10g}"

    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"

    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {_format_value(item)}"
            for key, item in value.items()
        )

    return str(value)


def _format_matrix(matrix: list[list[float]]) -> str:
    """Format a matrix as readable HTML."""
    rows = []

    for row in matrix:
        cells = "".join(
            f"<td>{escape(_format_value(value))}</td>"
            for value in row
        )
        rows.append(f"<tr>{cells}</tr>")

    return (
        '<table class="matrix">'
        "<tbody>"
        + "".join(rows)
        + "</tbody>"
        "</table>"
    )


def _format_operations(
    operations: list[dict[str, Any]],
) -> str:
    """Format symmetry operations."""
    if not operations:
        return "<p>No symmetry operations available.</p>"

    rows = []

    for operation in operations:
        operation_id = escape(str(operation.get("id", "")))
        symbol = escape(str(operation.get("symbol", "")))
        operation_type = escape(str(operation.get("type", "")))

        rows.append(
            "<tr>"
            f"<td>{operation_id}</td>"
            f"<td>{symbol}</td>"
            f"<td>{operation_type}</td>"
            "</tr>"
        )

    return (
        '<table class="operations">'
        "<thead>"
        "<tr>"
        "<th>ID</th>"
        "<th>Operation</th>"
        "<th>Type</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody>"
        "</table>"
    )


def _format_matrices(
    matrices: dict[str, Any],
) -> str:
    """Format Cartesian transformation matrices."""
    if not matrices:
        return "<p>No transformation matrices available.</p>"

    sections = []

    for operation_id, result in matrices.items():
        if isinstance(result, dict):
            matrix = result.get("matrix")
        else:
            matrix = result

        if matrix is None:
            continue

        sections.append(
            "<section class=\"matrix-section\">"
            f"<h4>{escape(str(operation_id))}</h4>"
            f"{_format_matrix(matrix)}"
            "</section>"
        )

    return "".join(sections)


def _format_representation(
    representation: dict[str, Any],
) -> str:
    """Format representation matrices."""
    if not representation:
        return "<p>No representation data available.</p>"

    representation_matrices = representation.get(
        "representation_matrices",
        {},
    )

    if not representation_matrices:
        return "<p>No representation matrices available.</p>"

    sections = []

    for operation_id, matrix in representation_matrices.items():
        sections.append(
            "<section class=\"matrix-section\">"
            f"<h4>{escape(str(operation_id))}</h4>"
            f"{_format_matrix(matrix)}"
            "</section>"
        )

    return "".join(sections)


def _format_characters(
    characters: dict[str, Any],
) -> str:
    """Format representation characters."""
    if not characters:
        return "<p>No characters available.</p>"

    rows = []

    for operation_id, character in characters.items():
        rows.append(
            "<tr>"
            f"<td>{escape(str(operation_id))}</td>"
            f"<td>{escape(_format_value(character))}</td>"
            "</tr>"
        )

    return (
        '<table class="characters">'
        "<thead>"
        "<tr>"
        "<th>Operation</th>"
        "<th>Character χ(g)</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody>"
        "</table>"
    )


def _verification_status(
    verification: dict[str, Any],
) -> tuple[str, str]:
    """
    Return a human-readable verification status.

    PASS is the only verified state.
    """
    if not isinstance(verification, dict):
        return "NOT VERIFIED", "not-verified"

    status = str(
        verification.get("status", "NOT VERIFIED")
    ).upper()

    if status == "PASS":
        return "✓ VERIFIED", "verified"

    if status == "FLAG":
        return "⚠ NEEDS REVIEW", "flagged"

    return "NOT VERIFIED", "not-verified"


def _format_verification(
    verification: dict[str, Any],
) -> str:
    """Format verification checks and errors."""
    if not verification:
        return "<p>Verification has not been performed.</p>"

    status = str(
        verification.get("status", "NOT VERIFIED")
    ).upper()

    checks = verification.get("checks", {})
    errors = verification.get("errors", [])

    html_parts = [
        f"<p><strong>Status:</strong> {escape(status)}</p>"
    ]

    if checks:
        rows = []

        for name, result in checks.items():
            rows.append(
                "<tr>"
                f"<td>{escape(str(name))}</td>"
                f"<td>{escape(str(result))}</td>"
                "</tr>"
            )

        html_parts.append(
            '<table class="verification">'
            "<thead>"
            "<tr>"
            "<th>Check</th>"
            "<th>Result</th>"
            "</tr>"
            "</thead>"
            "<tbody>"
            + "".join(rows)
            + "</tbody>"
            "</table>"
        )

    if errors:
        html_parts.append("<h4>Errors</h4><ul>")

        for error in errors:
            html_parts.append(
                f"<li>{escape(str(error))}</li>"
            )

        html_parts.append("</ul>")

    return "".join(html_parts)


def _format_group_theory(
    group_theory: dict[str, Any],
) -> str:
    """
    Format the point-group character table and irreducible-representation
    reduction produced by the registry-driven full_analysis tool.

    Works for any point group, not just D3h, since the data comes entirely
    from app.science.point_group_registry / app.science.reduction.
    """
    if not group_theory:
        return (
            "<p>Reduction into irreducible representations has not "
            "been performed.</p>"
        )

    classes = group_theory.get("classes", [])
    character_table = group_theory.get("character_table", {})
    reduction = group_theory.get("reduction", {})

    html_parts: list[str] = []

    if classes and character_table:
        header_cells = "".join(
            f"<th>{escape(str(class_symbol))}</th>" for class_symbol in classes
        )

        rows = []
        for irrep, row in character_table.items():
            cells = "".join(
                f"<td>{_format_value(value)}</td>" for value in row
            )
            rows.append(
                f"<tr><td>{escape(str(irrep))}</td>{cells}</tr>"
            )

        html_parts.append(
            "<h3>Character Table</h3>"
            '<table class="matrix">'
            f"<thead><tr><th></th>{header_cells}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )

    reducible_characters = group_theory.get("reducible_characters")

    if classes and reducible_characters:
        header_cells = "".join(
            f"<th>{escape(str(class_symbol))}</th>" for class_symbol in classes
        )
        value_cells = "".join(
            f"<td>{_format_value(value)}</td>"
            for value in reducible_characters
        )
        html_parts.append(
            "<h3>Reducible Representation (Cartesian basis)</h3>"
            '<table class="matrix">'
            f"<thead><tr>{header_cells}</tr></thead>"
            f"<tbody><tr>{value_cells}</tr></tbody>"
            "</table>"
        )

    if reduction:
        summary = reduction.get("summary")
        formula = reduction.get("formula")
        irrep_basis = reduction.get("irrep_basis_functions", {})

        if summary:
            html_parts.append(
                f"<p><strong>Decomposition:</strong> {escape(str(summary))}</p>"
            )

        if formula:
            html_parts.append(
                f'<p class="formula">{escape(str(formula))}</p>'
            )

        if irrep_basis:
            rows = []
            for irrep, basis_labels in irrep_basis.items():
                labels = ", ".join(str(item) for item in basis_labels) or "—"
                rows.append(
                    "<tr>"
                    f"<td>{escape(str(irrep))}</td>"
                    f"<td>{escape(labels)}</td>"
                    "</tr>"
                )

            html_parts.append(
                "<h3>Basis Functions of Contributing Irreps</h3>"
                '<table class="verification">'
                "<thead><tr><th>Irrep</th><th>Basis</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody>"
                "</table>"
            )

    if not html_parts:
        return "<p>No group-theory reduction data is available.</p>"

    return "".join(html_parts)


def generate_report(session: Any) -> str:
    """
    Generate a complete HTML research report from a session.

    The session can be a ResearchSession object or any object exposing
    the same attributes.
    """
    molecule = session.molecule or "Unknown"
    point_group = session.point_group or "Unknown"

    operations = session.operations or []
    matrices = session.matrices or {}
    representation = session.representation or {}
    characters = session.characters or {}
    verification = session.verification or {}
    group_theory = getattr(session, "group_theory", None) or {}

    verification_label, verification_class = _verification_status(
        verification
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>
        {escape(str(molecule))} Symmetry Analysis - VoiceLab
    </title>

    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.5;
            margin: 0;
            padding: 40px;
            background: #f7f7f7;
            color: #222;
        }}

        .report {{
            max-width: 1000px;
            margin: auto;
            background: white;
            padding: 40px;
            border-radius: 12px;
        }}

        h1, h2, h3, h4 {{
            margin-top: 0;
        }}

        .header {{
            border-bottom: 1px solid #ddd;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}

        .summary {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin: 20px 0;
        }}

        .summary-card {{
            padding: 16px;
            border: 1px solid #ddd;
            border-radius: 8px;
        }}

        .verification-badge {{
            display: inline-block;
            margin: 20px 0;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: bold;
        }}

        .verified {{
            border: 2px solid #222;
        }}

        .flagged {{
            border: 2px solid #777;
        }}

        .not-verified {{
            border: 1px solid #aaa;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0 24px;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 8px 10px;
            text-align: left;
        }}

        th {{
            font-weight: 600;
        }}

        .matrix-section {{
            margin-bottom: 24px;
        }}

        .matrix {{
            width: auto;
        }}

        .matrix td {{
            min-width: 55px;
            text-align: center;
            font-family: monospace;
        }}

        .section {{
            margin-top: 40px;
        }}

        .formula {{
            font-family: monospace;
            padding: 12px;
            border-left: 3px solid #444;
            background: #f5f5f5;
        }}

        footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 0.9rem;
        }}
    </style>
</head>

<body>
    <main class="report">

        <header class="header">
            <h1>VoiceLab Research Report</h1>
            <p>Scientific Molecular Symmetry Analysis</p>
        </header>

        <section class="summary">
            <div class="summary-card">
                <strong>Molecule</strong>
                <div>{escape(str(molecule))}</div>
            </div>

            <div class="summary-card">
                <strong>Point Group</strong>
                <div>{escape(str(point_group))}</div>
            </div>
        </section>

        <div class="verification-badge {verification_class}">
            {escape(verification_label)}
        </div>

        <section class="section">
            <h2>Symmetry Operations</h2>
            {_format_operations(operations)}
        </section>

        <section class="section">
            <h2>Cartesian Transformation Matrices</h2>

            <p class="formula">
                r' = M r
            </p>

            {_format_matrices(matrices)}
        </section>

        <section class="section">
            <h2>Representation</h2>

            <p class="formula">
                χ(g) = Tr[D(g)]
            </p>

            {_format_representation(representation)}
        </section>

        <section class="section">
            <h2>Characters</h2>

            {_format_characters(characters)}
        </section>

        <section class="section">
            <h2>Irreducible Representation Reduction</h2>

            <p class="formula">
                n_i = (1/h) &Sigma;<sub>C</sub> g<sub>C</sub> &chi;<sub>&Gamma;</sub>(C) &chi;<sub>i</sub>(C)
            </p>

            {_format_group_theory(group_theory)}
        </section>

        <section class="section">
            <h2>Verification</h2>

            {_format_verification(verification)}
        </section>

        <footer>
            Generated by VoiceLab.
            Scientific calculations are produced by the deterministic
            calculation layer and independently checked before being
            marked as verified.
        </footer>

    </main>
</body>
</html>
"""


def generate_report_from_dict(
    session_data: dict[str, Any],
) -> str:
    """
    Generate a report directly from a session dictionary.

    Useful when the application state has already been serialized.
    """
    class SessionView:
        pass

    session = SessionView()

    session.molecule = session_data.get("molecule")
    session.point_group = session_data.get("point_group")
    session.operations = session_data.get("operations", [])
    session.matrices = session_data.get("matrices", {})
    session.representation = session_data.get("representation", {})
    session.characters = session_data.get("characters", {})
    session.verification = session_data.get("verification", {})
    session.group_theory = session_data.get("group_theory", {})

    return generate_report(session)