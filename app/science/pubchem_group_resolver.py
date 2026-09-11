"""
Map verified geometry operations to registered point-group class signatures.

This module deliberately delegates final point-group identification to the
existing registry. It never trusts an external point-group label.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def operation_class_signature(
    operations: list[dict[str, Any]],
) -> Counter[str]:
    """Count canonical operation classes supplied by a classifier."""
    return Counter(
        str(operation["class"])
        for operation in operations
        if operation.get("class")
    )


def match_registered_group(
    verified_class_counts: Counter[str],
    point_group_registry,
) -> str | None:
    """Return a unique registered group whose class signature matches."""
    matches = []
    for definition in point_group_registry._definitions.values():
        expected = Counter({
            str(cls): int(size)
            for cls, size in definition.class_sizes.items()
        })
        if verified_class_counts == expected:
            matches.append(definition.point_group_id)
    return matches[0] if len(matches) == 1 else None
