"""Automatic point-group character-table discovery and registry.

Drop a module into app/science/point_groups/ and expose:

    POINT_GROUP_ID = "..."
    get_point_group_data() -> dict

The registry discovers the module automatically, exactly like
app.science.molecule_registry discovers molecules. Adding a new point
group here does not require editing this file, the molecule registry,
the analysis tools, or the voice agent.

This module is intentionally independent of app.science.d3h, so the
existing BF3/D3h pipeline in app.tools.bf3_analysis keeps working
completely unchanged.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any


POINT_GROUPS_PACKAGE = "app.science.point_groups"


@dataclass(frozen=True)
class PointGroupDefinition:
    """Validated point-group character-table data exposed by the registry."""

    point_group_id: str
    order: int
    classes: list[str]
    class_sizes: dict[str, int]
    irreps: list[str]
    irrep_dimensions: dict[str, int]
    character_table: dict[str, list[float]]
    basis_functions: dict[str, list[str]]


class PointGroupRegistry:
    """Automatically discover and expose point-group character tables."""

    def __init__(self, package_name: str = POINT_GROUPS_PACKAGE) -> None:
        self.package_name = package_name
        self._definitions: dict[str, PointGroupDefinition] = {}
        self._errors: dict[str, str] = {}
        self.discover()

    def discover(self) -> dict[str, PointGroupDefinition]:
        """Scan the point-group package and import every definition module."""
        self._definitions.clear()
        self._errors.clear()

        package = importlib.import_module(self.package_name)

        for module_info in pkgutil.iter_modules(package.__path__):
            if module_info.name.startswith("_"):
                continue

            module_name = f"{self.package_name}.{module_info.name}"

            try:
                module = importlib.import_module(module_name)
                definition = self._load_definition(module)
                self._definitions[definition.point_group_id.upper()] = definition
            except Exception as exc:
                self._errors[module_name] = str(exc)

        return dict(self._definitions)

    def _load_definition(self, module: ModuleType) -> PointGroupDefinition:
        getter = getattr(module, "get_point_group_data", None)
        if not callable(getter):
            raise ValueError(
                "Point group module must define get_point_group_data()."
            )

        data = getter()

        if not isinstance(data, dict):
            raise TypeError("get_point_group_data() must return a dict.")

        required = (
            "id",
            "order",
            "classes",
            "class_sizes",
            "irreps",
            "irrep_dimensions",
            "character_table",
        )

        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(
                f"Missing required point group fields: {', '.join(missing)}"
            )

        point_group_id = str(data["id"]).strip()
        if not point_group_id:
            raise ValueError("Point group id cannot be empty.")

        classes = data["classes"]
        if not isinstance(classes, list) or not classes:
            raise TypeError("Point group classes must be a non-empty list.")

        class_sizes = data["class_sizes"]
        if not isinstance(class_sizes, dict):
            raise TypeError("Point group class_sizes must be a dict.")

        missing_sizes = [c for c in classes if c not in class_sizes]
        if missing_sizes:
            raise ValueError(
                "class_sizes is missing entries for: "
                f"{', '.join(missing_sizes)}"
            )

        order = int(data["order"])
        computed_order = sum(int(class_sizes[c]) for c in classes)
        if computed_order != order:
            raise ValueError(
                f"Declared order ({order}) does not match the sum of "
                f"class sizes ({computed_order})."
            )

        irreps = data["irreps"]
        if not isinstance(irreps, list) or not irreps:
            raise TypeError("Point group irreps must be a non-empty list.")

        irrep_dimensions = data["irrep_dimensions"]
        if not isinstance(irrep_dimensions, dict):
            raise TypeError("Point group irrep_dimensions must be a dict.")

        character_table = data["character_table"]
        if not isinstance(character_table, dict):
            raise TypeError("Point group character_table must be a dict.")

        for irrep in irreps:
            if irrep not in character_table:
                raise ValueError(
                    f"character_table is missing irrep {irrep!r}."
                )
            row = character_table[irrep]
            if not isinstance(row, list) or len(row) != len(classes):
                raise ValueError(
                    f"character_table[{irrep!r}] must have exactly "
                    f"{len(classes)} entries (one per class)."
                )

        # Sum of squared irrep dimensions must equal the group order.
        dimension_check = sum(
            int(irrep_dimensions.get(irrep, 0)) ** 2 for irrep in irreps
        )
        if dimension_check != order:
            raise ValueError(
                "Sum of squared irrep dimensions "
                f"({dimension_check}) does not equal the group order "
                f"({order})."
            )

        basis_functions = data.get("basis_functions", {})
        if not isinstance(basis_functions, dict):
            raise TypeError("Point group basis_functions must be a dict.")

        return PointGroupDefinition(
            point_group_id=point_group_id,
            order=order,
            classes=list(classes),
            class_sizes={c: int(class_sizes[c]) for c in classes},
            irreps=list(irreps),
            irrep_dimensions={
                irrep: int(irrep_dimensions.get(irrep, 1)) for irrep in irreps
            },
            character_table={
                irrep: [float(v) for v in character_table[irrep]]
                for irrep in irreps
            },
            basis_functions={
                irrep: list(basis_functions.get(irrep, [])) for irrep in irreps
            },
        )

    def get(self, point_group: str) -> PointGroupDefinition:
        """Return a point-group definition by id (case-insensitive)."""
        key = self._normalize(point_group)

        if key in self._definitions:
            return self._definitions[key]

        available = ", ".join(sorted(self._definitions))
        raise KeyError(
            f"Point group '{point_group}' is not registered. "
            f"Available point groups: {available or 'none'}."
        )

    def has(self, point_group: str) -> bool:
        try:
            self.get(point_group)
            return True
        except KeyError:
            return False

    def list(self) -> list[dict[str, Any]]:
        """Return compact metadata for all successfully loaded point groups."""
        return [
            {
                "id": definition.point_group_id,
                "order": definition.order,
                "classes": list(definition.classes),
                "irreps": list(definition.irreps),
            }
            for definition in sorted(
                self._definitions.values(),
                key=lambda item: item.point_group_id,
            )
        ]

    def errors(self) -> dict[str, str]:
        """Return modules that failed discovery without crashing the app."""
        return dict(self._errors)

    @staticmethod
    def _normalize(value: str) -> str:
        return str(value).strip().upper()


# One process-wide registry for the application.
registry = PointGroupRegistry()


def get_point_group(point_group: str) -> PointGroupDefinition:
    return registry.get(point_group)


def list_point_groups() -> list[dict[str, Any]]:
    return registry.list()


def refresh_point_group_registry() -> list[dict[str, Any]]:
    registry.discover()
    return registry.list()
