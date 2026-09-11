"""Modele i parser odpowiedzi API dla planszy reactor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


GridPos = tuple[int, int]
FLAG_REGEX = re.compile(r"\{FLG:[A-Za-z0-9_\-]+\}")


@dataclass(slots=True)
class Block:
    """Reprezentuje pionowy blok reaktora o długości dwóch pól.

    Atrybuty:
        column: Kolumna bloku (1..7).
        top_row: Wiersz górnego segmentu bloku.
        direction: Kierunek następnego ruchu (`up` lub `down`).
    """

    column: int
    top_row: int
    direction: str

    @property
    def cells(self) -> set[GridPos]:
        """Zwraca pola zajmowane przez blok.

        Returns:
            Zbiór pozycji `(kolumna, wiersz)` zajętych przez blok.
        """

        return {(self.column, self.top_row), (self.column, self.top_row + 1)}


@dataclass(slots=True)
class BoardState:
    """Znormalizowany stan planszy wykorzystywany przez logikę ruchu.

    Atrybuty:
        raw_response: Oryginalna odpowiedź API.
        robot_col: Kolumna robota.
        robot_row: Wiersz robota.
        goal_col: Kolumna celu.
        goal_row: Wiersz celu.
        blocks: Lista bloków.
        board_rows: Widok planszy jako lista wierszy.
        notes: Dodatkowe adnotacje parsera.
    """

    raw_response: dict[str, Any]
    robot_col: int = 1
    robot_row: int = 5
    goal_col: int = 7
    goal_row: int = 5
    blocks: list[Block] = field(default_factory=list)
    board_rows: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def at_goal(self) -> bool:
        """Sprawdza, czy robot stoi na domyślnym celu planszy.

        Returns:
            `True`, jeśli pozycja robota pokrywa się z celem `G`.
        """

        return self.robot_col == self.goal_col and self.robot_row == self.goal_row


def parse_board_state(response: dict[str, Any]) -> BoardState:
    """Parsuje odpowiedź API do obiektu `BoardState`.

    Args:
        response: Odpowiedź endpointu `/verify`.

    Returns:
        Znormalizowany stan planszy.
    """

    state = BoardState(raw_response=response)
    rows = _extract_board_rows(response)
    if rows:
        state.board_rows = rows
        state.notes.append("board_rows_extracted")

    robot = _extract_position(response, ("robot", "player", "position", "agent"))
    if robot is None and rows:
        robot = _find_marker(rows, "P")
    if robot:
        state.robot_col, state.robot_row = robot
    else:
        state.notes.append("robot_position_fallback")

    goal = _extract_position(response, ("goal", "target", "destination"))
    if goal is None and rows:
        goal = _find_marker(rows, "G")
    if goal:
        state.goal_col, state.goal_row = goal

    state.blocks = _extract_blocks(response, rows)
    if not state.blocks and rows:
        state.blocks = _infer_blocks_from_rows(rows)
        if state.blocks:
            state.notes.append("blocks_inferred")

    return state


def find_flag_in_payload(payload: Any) -> str | None:
    """Wyszukuje pierwszą flagę `{FLG:...}` w strukturze odpowiedzi.

    Args:
        payload: Dowolna struktura danych odpowiedzi API.

    Returns:
        Znaleziona flaga albo `None`.
    """

    for value in _walk_values(payload):
        if not isinstance(value, str):
            continue
        match = FLAG_REGEX.search(value)
        if match:
            return match.group(0)
    return None


def to_serializable_state(state: BoardState) -> dict[str, Any]:
    """Konwertuje `BoardState` do słownika gotowego do zapisu JSON.

    Args:
        state: Stan planszy.

    Returns:
        Słownik z kluczowymi polami stanu.
    """

    return {
        "robot": {"col": state.robot_col, "row": state.robot_row},
        "goal": {"col": state.goal_col, "row": state.goal_row},
        "board_rows": state.board_rows,
        "blocks": [
            {
                "column": block.column,
                "top_row": block.top_row,
                "direction": block.direction,
                "cells": sorted(block.cells),
            }
            for block in state.blocks
        ],
        "notes": state.notes,
        "at_goal": state.at_goal,
    }


def _extract_board_rows(payload: Any) -> list[str]:
    """Wydobywa planszę 7x5 z odpowiedzi API.

    Args:
        payload: Odpowiedź API.

    Returns:
        Lista pięciu wierszy długości siedem lub pusta lista.
    """

    candidates: list[Any] = []
    for key in ("board", "map", "grid", "reactor", "state"):
        value = _deep_find_key(payload, key)
        if value is not None:
            candidates.append(value)

    for candidate in candidates:
        normalized = _normalize_rows(candidate)
        if normalized:
            return normalized
    return []


def _normalize_rows(candidate: Any) -> list[str]:
    """Normalizuje różne reprezentacje planszy do listy wierszy.

    Args:
        candidate: Potencjalna reprezentacja planszy.

    Returns:
        Lista poprawnych wierszy planszy albo pusta lista.
    """

    rows: list[str] = []
    if isinstance(candidate, str):
        rows = [_normalize_row(line) for line in candidate.splitlines() if line.strip()]
    elif isinstance(candidate, list):
        if all(isinstance(item, str) for item in candidate):
            rows = [_normalize_row(item) for item in candidate]
        elif all(isinstance(item, list) for item in candidate):
            rows = [_normalize_row("".join(str(cell) for cell in item)) for item in candidate]

    valid = [row for row in rows if len(row) == 7]
    if len(valid) >= 5:
        return valid[:5]
    return []


def _normalize_row(raw: str) -> str:
    """Czyści pojedynczy wiersz planszy do dozwolonych symboli.

    Args:
        raw: Surowy wiersz planszy.

    Returns:
        Oczyszczony wiersz.
    """

    allowed = {"P", "G", "B", ".", "↑", "↓", "^", "v"}
    row = "".join(char for char in raw if char in allowed)
    return row.replace("^", "↑").replace("v", "↓")[:7]


def _extract_position(payload: Any, keys: tuple[str, ...]) -> GridPos | None:
    """Wydobywa pozycję `(col,row)` na podstawie listy kluczy.

    Args:
        payload: Odpowiedź API.
        keys: Klucze do wyszukania.

    Returns:
        Pozycja `(kolumna, wiersz)` albo `None`.
    """

    for key in keys:
        value = _deep_find_key(payload, key)
        pos = _parse_position_dict(value)
        if pos is not None:
            return pos
    return None


def _parse_position_dict(value: Any) -> GridPos | None:
    """Parsuje słownik pozycji do formatu `(col,row)`.

    Args:
        value: Potencjalny słownik pozycji.

    Returns:
        Pozycja albo `None`.
    """

    if not isinstance(value, dict):
        return None
    col = value.get("col", value.get("column", value.get("x")))
    row = value.get("row", value.get("y"))
    if isinstance(col, int) and isinstance(row, int):
        return col, row
    return None


def _find_marker(rows: list[str], marker: str) -> GridPos | None:
    """Wyszukuje pozycję wskazanego symbolu na planszy.

    Args:
        rows: Wiersze planszy.
        marker: Szukany symbol (`P` lub `G`).

    Returns:
        Pozycja symbolu albo `None`.
    """

    for row_idx, row_text in enumerate(rows, start=1):
        col_idx = row_text.find(marker)
        if col_idx != -1:
            return col_idx + 1, row_idx
    return None


def _extract_blocks(payload: Any, rows: list[str]) -> list[Block]:
    """Wydobywa listę bloków z odpowiedzi lub z planszy.

    Args:
        payload: Odpowiedź API.
        rows: Wiersze planszy.

    Returns:
        Lista bloków.
    """

    for key in ("blocks", "obstacles", "reactor_blocks"):
        value = _deep_find_key(payload, key)
        parsed = _parse_blocks_list(value)
        if parsed:
            return parsed
    return _infer_blocks_from_rows(rows)


def _parse_blocks_list(value: Any) -> list[Block]:
    """Parsuje listę bloków ze słowników API.

    Args:
        value: Potencjalna lista bloków.

    Returns:
        Lista sparsowanych bloków.
    """

    result: list[Block] = []
    if not isinstance(value, list):
        return result
    for item in value:
        if not isinstance(item, dict):
            continue
        col = item.get("col", item.get("column", item.get("x")))
        top_row = item.get("top_row", item.get("row", item.get("y")))
        direction = _normalize_direction(item.get("direction", item.get("dir", "down")))
        if isinstance(col, int) and isinstance(top_row, int):
            result.append(Block(column=col, top_row=top_row, direction=direction))
    return result


def _infer_blocks_from_rows(rows: list[str]) -> list[Block]:
    """Inferuje bloki na podstawie symboli `B` widocznych na planszy.

    Args:
        rows: Wiersze planszy.

    Returns:
        Lista bloków z domyślnym kierunkiem `down`, jeśli brak strzałek.
    """

    if not rows:
        return []

    blocks: list[Block] = []
    for col in range(1, 8):
        rows_with_b = [row for row in range(1, 6) if rows[row - 1][col - 1] == "B"]
        if len(rows_with_b) < 2:
            continue
        top = min(rows_with_b)
        direction = "down"
        if any(_has_neighbor_arrow(rows, col, row, "↑") for row in rows_with_b):
            direction = "up"
        blocks.append(Block(column=col, top_row=top, direction=direction))
    return blocks


def _has_neighbor_arrow(rows: list[str], col: int, row: int, arrow: str) -> bool:
    """Sprawdza, czy obok pola znajduje się wskazana strzałka.

    Args:
        rows: Wiersze planszy.
        col: Kolumna bazowa.
        row: Wiersz bazowy.
        arrow: Szukana strzałka.

    Returns:
        `True`, gdy strzałka znajduje się po lewej lub prawej stronie.
    """

    for d_col in (-1, 1):
        c = col + d_col
        if 1 <= c <= 7 and rows[row - 1][c - 1] == arrow:
            return True
    return False


def _normalize_direction(value: Any) -> str:
    """Normalizuje kierunek ruchu bloku.

    Args:
        value: Dowolna reprezentacja kierunku.

    Returns:
        Kierunek `up` albo `down`.
    """

    raw = str(value).strip().lower()
    if raw in {"up", "u", "-1", "↑", "north"}:
        return "up"
    return "down"


def _deep_find_key(payload: Any, target_key: str) -> Any:
    """Rekurencyjnie wyszukuje pierwszą wartość pod wskazanym kluczem.

    Args:
        payload: Struktura wejściowa.
        target_key: Klucz do znalezienia.

    Returns:
        Znaleziona wartość lub `None`.
    """

    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() == target_key.lower():
                return value
            nested = _deep_find_key(value, target_key)
            if nested is not None:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _deep_find_key(item, target_key)
            if nested is not None:
                return nested
    return None


def _walk_values(payload: Any) -> list[Any]:
    """Spłaszcza wartości z dowolnej zagnieżdżonej struktury.

    Args:
        payload: Struktura wejściowa.

    Returns:
        Lista wartości atomowych.
    """

    values: list[Any] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(_walk_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_walk_values(item))
    else:
        values.append(payload)
    return values
