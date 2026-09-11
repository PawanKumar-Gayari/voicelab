"""Registry-first PubChem fallback boundary.

This is the only intended entry point for future production wiring:
registered molecules always use the existing VoiceLab path; only a registry
miss is eligible for external lookup.

The function deliberately accepts injected callables so production code can
wire its existing PubChem client and Phase-4 resolver without hard-coding
network behavior here.
"""
from __future__ import annotations
from typing import Any, Callable

def registry_first(
    molecule: str,
    *,
    registry_has: Callable[[str], bool],
    local_analyze: Callable[[str], dict[str, Any]],
    external_analyze: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    if registry_has(molecule):
        return local_analyze(molecule)

    result = external_analyze(molecule)
    if not result.get("success"):
        return result

    # External results must carry explicit verification before being exposed
    # as scientific output.
    data = result.get("data") or {}
    verification = data.get("verification") or {}
    if verification.get("status") not in {"PASS", "VERIFIED"}:
        return {
            "success": False,
            "tool": "full_analysis",
            "data": None,
            "error": {
                "code": "EXTERNAL_VERIFICATION_REQUIRED",
                "message": "External geometry did not pass final verification.",
            },
        }
    return result
