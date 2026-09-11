"""Automatic molecule discovery and registry.

Drop a module into app/science/molecules/ and expose:

    MOLECULE_ID = "..."
    get_molecule_data() -> dict

The registry discovers the module automatically. Existing voice tools do
not need molecule-specific if/elif branches.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any


MOLECULES_PACKAGE = "app.science.molecules"


@dataclass(frozen=True)
class MoleculeDefinition:
    """Validated molecule definition exposed by the registry."""

    molecule_id: str
    name: str
    formula: str
    point_group: str
    coordinates: Any
    operations: list[dict]
    matrices: dict
    bonds: list[dict]


class MoleculeRegistry:
    """Automatically discover and expose molecule definitions."""

    def __init__(self, package_name: str = MOLECULES_PACKAGE) -> None:
        self.package_name = package_name
        self._definitions: dict[str, MoleculeDefinition] = {}
        self._errors: dict[str, str] = {}
        self.discover()

    def discover(self) -> dict[str, MoleculeDefinition]:
        """Scan the molecule package and import every definition module."""
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
                self._definitions[definition.molecule_id.upper()] = definition
            except Exception as exc:
                self._errors[module_name] = str(exc)

        return dict(self._definitions)

    def _load_definition(self, module: ModuleType) -> MoleculeDefinition:
        getter = getattr(module, "get_molecule_data", None)
        if not callable(getter):
            raise ValueError(
                "Molecule module must define get_molecule_data()."
            )

        data = getter()

        if not isinstance(data, dict):
            raise TypeError("get_molecule_data() must return a dict.")

        required = (
            "id",
            "name",
            "formula",
            "point_group",
            "coordinates",
            "operations",
        )

        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(
                f"Missing required molecule fields: {', '.join(missing)}"
            )

        molecule_id = str(data["id"]).strip().upper()
        if not molecule_id:
            raise ValueError("Molecule id cannot be empty.")

        operations = data["operations"]
        if not isinstance(operations, list):
            raise TypeError("Molecule operations must be a list.")

        matrices = data.get("matrices", {})
        if not isinstance(matrices, dict):
            raise TypeError("Molecule matrices must be a dict.")

        return MoleculeDefinition(
            molecule_id=molecule_id,
            name=str(data["name"]),
            formula=str(data["formula"]),
            point_group=str(data["point_group"]),
            coordinates=data["coordinates"],
            operations=operations,
            matrices=matrices,
            bonds=data.get("bonds", []),
        )

    def get(self, molecule: str) -> MoleculeDefinition:
        """Return a molecule definition by id/name/formula."""
        key = self._normalize(molecule)

        if key in self._definitions:
            return self._definitions[key]

        for definition in self._definitions.values():
            aliases = {
                self._normalize(definition.molecule_id),
                self._normalize(definition.name),
                self._normalize(definition.formula),
            }
            if key in aliases:
                return definition

        available = ", ".join(sorted(self._definitions))
        raise KeyError(
            f"Molecule '{molecule}' is not registered. "
            f"Available molecules: {available or 'none'}."
        )

    def has(self, molecule: str) -> bool:
        try:
            self.get(molecule)
            return True
        except KeyError:
            return False

    def list(self) -> list[dict[str, str]]:
        """Return compact metadata for all successfully loaded molecules."""
        return [
            {
                "id": definition.molecule_id,
                "name": definition.name,
                "formula": definition.formula,
                "point_group": definition.point_group,
            }
            for definition in sorted(
                self._definitions.values(),
                key=lambda item: item.molecule_id,
            )
        ]

    def errors(self) -> dict[str, str]:
        """Return modules that failed discovery without crashing the app."""
        return dict(self._errors)

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(str(value).strip().upper().split())


# One process-wide registry for the application.
registry = MoleculeRegistry()


def get_molecule(molecule: str) -> MoleculeDefinition:
    return registry.get(molecule)


def list_molecules() -> list[dict[str, str]]:
    return registry.list()


def refresh_molecule_registry() -> list[dict[str, str]]:
    registry.discover()
    return registry.list()
