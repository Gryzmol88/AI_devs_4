"""Planowanie kolejności przeszukania mapy i priorytetyzacji pól."""

from __future__ import annotations

from typing import Any

from .map_parser import collect_all_cells
from .models import PlanResult


def build_search_plan(
    map_payload: dict[str, Any],
    intel_cells: list[str] | None,
) -> PlanResult:
    """Buduje prosty plan przeszukania mapy.

    Priorytet:
    1) pola zasugerowane przez warstwę analityczną,
    2) pozostałe pola mapy.

    Args:
        map_payload: Surowe dane mapy z API.
        intel_cells: Opcjonalna lista pól priorytetowych.

    Returns:
        PlanResult: Plan zawierający posortowaną listę pól i notatkę.
    """

    all_cells = collect_all_cells(map_payload)
    unique_all = list(dict.fromkeys(all_cells))
    intel = [cell for cell in (intel_cells or []) if cell in unique_all]

    non_intel = [cell for cell in unique_all if cell not in intel]
    preferred = intel + non_intel
    notes = (
        "Plan laczy priorytety z analizy sygnalu z pelnym pokryciem mapy. "
        "Krytyczna logika kosztowa pozostaje deterministyczna."
    )
    return PlanResult(preferred_cells=preferred, notes=notes)

