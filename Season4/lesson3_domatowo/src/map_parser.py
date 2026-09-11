"""Narzędzia do parsowania mapy i pracy ze współrzędnymi planszy."""

from __future__ import annotations

from typing import Any


def to_cell_label(row: int, col: int) -> str:
    """Konwertuje współrzędne liczbowe na etykietę pola, np. `F6`.

    Args:
        row: Indeks wiersza od zera.
        col: Indeks kolumny od zera.

    Returns:
        str: Etykieta pola zgodna z konwencją litera+liczba.
    """

    return f"{chr(ord('A') + col)}{row + 1}"


def collect_all_cells(map_payload: dict[str, Any]) -> list[str]:
    """Zwraca listę pól mapy na podstawie danych z akcji `getMap`.

    Funkcja obsługuje różne formaty struktur mapy:
    - lista list pod kluczem `map`,
    - lista list pod kluczem `grid`,
    - bezpośrednia lista list.

    Args:
        map_payload: Surowa odpowiedź JSON z endpointu mapy.

    Returns:
        list[str]: Lista etykiet pól mapy w kolejności wierszowej.
    """

    map_node = map_payload.get("map")
    if isinstance(map_node, dict) and "grid" in map_node:
        grid = map_node.get("grid")
    else:
        grid = map_payload.get("grid") or map_payload
    if not isinstance(grid, list):
        return []
    if not grid or not isinstance(grid[0], list):
        return []

    cells: list[str] = []
    for row_index, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        for col_index, _ in enumerate(row):
            cells.append(to_cell_label(row_index, col_index))
    return cells
