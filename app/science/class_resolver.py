"""Generic operation-to-conjugacy-class resolution.

Operation definitions may use readable base symbols such as ``C3`` or
``sigma_v`` while point-group registries use canonical conjugacy-class
symbols such as ``2C3`` and ``3sigma_v``.

This module contains no molecule-specific data.
"""

from __future__ import annotations

import re


def resolve_operation_class(
    operation_class: str,
    point_group_classes: list[str],
    class_sizes: dict[str, int],
    operation_class_count: int,
) -> str:
    """Resolve a raw operation class to a registered conjugacy class."""

    raw = str(operation_class).strip()

    if not raw:
        raise ValueError("Operation class cannot be empty.")

    # Exact canonical class already registered.
    if raw in point_group_classes:
        expected_size = int(class_sizes.get(raw, 0))
        if expected_size != operation_class_count:
            raise ValueError(
                f"Operation class {raw!r} has {operation_class_count} "
                f"members, but registered class size is {expected_size}."
            )
        return raw

    # Match a registered class by removing its leading multiplicity.
    #
    # Examples:
    #   2C3       -> C3
    #   3sigma_v  -> sigma_v
    #   3C2'      -> C2'
    candidates: list[str] = []

    for registered in point_group_classes:
        match = re.match(r"^(\d+)(.+)$", registered)
        if not match:
            continue

        multiplicity = int(match.group(1))
        base_symbol = match.group(2)

        if (
            base_symbol == raw
            and multiplicity == operation_class_count
            and int(class_sizes.get(registered, 0)) == operation_class_count
        ):
            candidates.append(registered)

    if len(candidates) == 1:
        return candidates[0]

    if not candidates:
        raise ValueError(
            f"Operation class {raw!r} with "
            f"{operation_class_count} member(s) does not match any "
            f"registered point-group class. Expected one of: "
            f"{', '.join(point_group_classes)}."
        )

    raise ValueError(
        f"Operation class {raw!r} with "
        f"{operation_class_count} member(s) ambiguously matches: "
        f"{', '.join(candidates)}."
    )
