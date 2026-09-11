"""
VoiceLab PubChem 3D client.

External source only: this module fetches normalized raw molecular metadata.
It does NOT decide molecular symmetry or point group.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
USER_AGENT = "VoiceLab/1.0 (scientific symmetry research application)"
MIN_REQUEST_INTERVAL = 0.21  # stays below PubChem's 5 requests/sec guidance


class PubChemError(RuntimeError):
    """Raised when PubChem data cannot be retrieved or parsed."""


@dataclass(frozen=True)
class PubChemMolecule:
    cid: int
    name: str
    formula: str
    atoms: list[dict]
    bonds: list[dict]
    source: str = "pubchem"


_last_request = 0.0


def _get_json(url: str) -> dict:
    global _last_request
    delay = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request)
    if delay > 0:
        time.sleep(delay)

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read()
        _last_request = time.monotonic()
        return json.loads(payload.decode("utf-8"))
    except HTTPError as exc:
        raise PubChemError(f"PubChem HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise PubChemError("PubChem request failed.") from exc
    except json.JSONDecodeError as exc:
        raise PubChemError("PubChem returned invalid JSON.") from exc


def resolve_cid(identifier: str) -> int:
    """Resolve a molecule name/formula/identifier to a PubChem CID."""
    value = str(identifier).strip()
    if not value:
        raise PubChemError("Molecule identifier cannot be empty.")

    url = f"{PUBCHEM_BASE}/compound/name/{quote(value, safe='')}/cids/JSON"
    data = _get_json(url)
    cids = ((data.get("IdentifierList") or {}).get("CID") or [])
    if not cids:
        raise PubChemError(f"No PubChem compound found for '{value}'.")
    return int(cids[0])


def fetch_3d(identifier: str) -> PubChemMolecule:
    """Fetch the first available PubChem 3D conformer for a compound."""
    cid = resolve_cid(identifier)

    url = (
        f"{PUBCHEM_BASE}/compound/cid/{cid}/record/JSON"
        "?record_type=3d&response_type=display"
    )
    record = _get_json(url)

    compounds = record.get("PC_Compounds") or []
    if not compounds:
        raise PubChemError(f"PubChem has no 3D record for CID {cid}.")

    compound = compounds[0]
    atoms_section = compound.get("atoms") or {}
    elements = atoms_section.get("element") or []
    coords = ((compound.get("coords") or [{}])[0])
    conformers = coords.get("conformers") or []
    if not conformers:
        raise PubChemError(f"PubChem has no 3D conformer for CID {cid}.")

    conformer = conformers[0]
    xs = conformer.get("x") or []
    ys = conformer.get("y") or []
    zs = conformer.get("z") or []

    if not (len(elements) == len(xs) == len(ys) == len(zs)) or not elements:
        raise PubChemError(f"Invalid 3D coordinate arrays for CID {cid}.")

    # PubChem 3D records encode atoms.element as atomic numbers.
    # Normalize them to chemical element symbols before exposing the
    # geometry to the rest of VoiceLab.
    periodic_symbols = {
        1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C",
        7: "N", 8: "O", 9: "F", 10: "Ne", 11: "Na", 12: "Mg",
        13: "Al", 14: "Si", 15: "P", 16: "S", 17: "Cl", 18: "Ar",
        19: "K", 20: "Ca", 21: "Sc", 22: "Ti", 23: "V", 24: "Cr",
        25: "Mn", 26: "Fe", 27: "Co", 28: "Ni", 29: "Cu", 30: "Zn",
        31: "Ga", 32: "Ge", 33: "As", 34: "Se", 35: "Br", 36: "Kr",
        37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo",
        43: "Tc", 44: "Ru", 45: "Rh", 46: "Pd", 47: "Ag", 48: "Cd",
        49: "In", 50: "Sn", 51: "Sb", 52: "Te", 53: "I", 54: "Xe",
        55: "Cs", 56: "Ba", 57: "La", 58: "Ce", 59: "Pr", 60: "Nd",
        61: "Pm", 62: "Sm", 63: "Eu", 64: "Gd", 65: "Tb", 66: "Dy",
        67: "Ho", 68: "Er", 69: "Tm", 70: "Yb", 71: "Lu", 72: "Hf",
        73: "Ta", 74: "W", 75: "Re", 76: "Os", 77: "Ir", 78: "Pt",
        79: "Au", 80: "Hg", 81: "Tl", 82: "Pb", 83: "Bi", 84: "Po",
        85: "At", 86: "Rn", 87: "Fr", 88: "Ra", 89: "Ac", 90: "Th",
        91: "Pa", 92: "U", 93: "Np", 94: "Pu", 95: "Am", 96: "Cm",
        97: "Bk", 98: "Cf", 99: "Es", 100: "Fm", 101: "Md", 102: "No",
        103: "Lr", 104: "Rf", 105: "Db", 106: "Sg", 107: "Bh",
        108: "Hs", 109: "Mt", 110: "Ds", 111: "Rg", 112: "Cn",
        113: "Nh", 114: "Fl", 115: "Mc", 116: "Lv", 117: "Ts", 118: "Og",
    }

    normalized_elements = []
    for element in elements:
        if isinstance(element, int):
            symbol = periodic_symbols.get(element)
            if symbol is None:
                raise PubChemError(f"Unknown PubChem atomic number: {element}.")
        else:
            symbol = str(element)
        normalized_elements.append(symbol)

    atoms = [
        {
            "label": f"{element}{index + 1}",
            "element": element,
            "coord": [float(xs[index]), float(ys[index]), float(zs[index])],
        }
        for index, element in enumerate(normalized_elements)
    ]

    bonds = []
    for bond in compound.get("bonds", {}).get("aid1", []):
        pass
    aid1 = compound.get("bonds", {}).get("aid1", [])
    aid2 = compound.get("bonds", {}).get("aid2", [])
    orders = compound.get("bonds", {}).get("order", [])
    for index, (a, b) in enumerate(zip(aid1, aid2)):
        bonds.append({
            "from": int(a) - 1,
            "to": int(b) - 1,
            "order": int(orders[index]) if index < len(orders) else 1,
        })

    props = compound.get("props") or []
    formula = ""
    name = f"CID {cid}"

    for prop in props:
        urn = prop.get("urn") or {}
        label = urn.get("label")
        name_field = urn.get("name")
        value = prop.get("value") or {}

        if label == "Compound" and name_field == "Canonicalized" and "sval" in value:
            name = str(value["sval"])

        if label == "Molecular Formula" and "sval" in value:
            formula = str(value["sval"])

    # PubChem 3D records do not always include Molecular Formula
    # in the record properties. Derive a deterministic Hill-system
    # formula from the actual atom elements as a safe metadata fallback.
    if not formula:
        counts = {}
        for element in normalized_elements:
            symbol = str(element)
            counts[symbol] = counts.get(symbol, 0) + 1

        ordered_elements = []
        if "C" in counts:
            ordered_elements.append("C")
        if "H" in counts:
            ordered_elements.append("H")
        ordered_elements.extend(
            sorted(
                symbol
                for symbol in counts
                if symbol not in {"C", "H"}
            )
        )

        formula = "".join(
            symbol + (str(counts[symbol]) if counts[symbol] != 1 else "")
            for symbol in ordered_elements
        )

    return PubChemMolecule(
        cid=cid,
        name=name,
        formula=formula,
        atoms=atoms,
        bonds=bonds,
    )
