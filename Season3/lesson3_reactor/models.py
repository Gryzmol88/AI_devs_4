"""Modele i parser odpowiedzi API dla zadania reactor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GridPos = tuple[int, int]


@dataclass(slots=True)
class Block:
    """Reprezentuje pionowy bloczek reaktora o długości dwóch pól.

    Atrybuty:
        column: Kolumna bloczka (1..7).
        top_row: Wiersz górnego segmentu bloczka (1..5).
        direction: Kierunek kolejnego ruchu: `up` lub `down`.
    """

    column: int
    top_row: int
    direction: str

    @property
    def cells(self) -> set[GridPos]:
        """Zwraca aktualnie zajmowane pola bloczka.

        Returns:
            Zbiór pozycji `(kolumna, wiersz)` zajętych przez bloczek.
        """

        return {(self.column, self.top_row), (self.column, self.top_row + 1)}


@dataclass(slots=True)
class BoardState:
    """Znormalizowany stan planszy potrzebny do podejmowania decyzji.

    Atrybuty:
        raw_response: Oryginalna odpowiedź API.
        robot_col: Kolumna robota na dolnym wierszu.
        robot_row: Wiersz robota.
        goal_col: Kolumna celu.
        goal_row: Wiersz celu.
        blocks: Lista bloczków reaktora.
        board_rows: Tekstowy widok planszy 7x5, gdy udało się go odczytać.
        notes: Dodatkowe uwagi parsera.
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
    def reached_goal(self) -> bool:
        """Sprawdza, czy robot jest na polu docelowym.

        Returns:
            `True`, gdy pozycja robota jest równa pozycji celu.
        """

        return self.robot_col == self.goal_col and self.robot_row == self.goal_row


def parse_board_state(response: dict[str, Any]) -> BoardState:
    """Parsuje odpowiedź API do struktury `BoardState`.

    Args:
        response: Słownik odpowiedzi endpointu `/verify`.

    Returns:
        Znormalizowany stan planszy z pozycją robota i bloczkami.
    """

    state = BoardState(raw_response=response)

    board_rows = _extract_board_rows(response)
    if board_rows:
        state.board_rows = board_rows
        state.notes.append("board_rows_extracted")

    robot = _extract_robot_position(response)
    if robot is None and board_rows:
        robot = _find_marker_position(board_rows, "P")
    if robot is not None:
        state.robot_col, state.robot_row = robot
    else:
        state.notes.append("robot_position_fallback")

    goal = _extract_goal_position(response)
    if goal is None and board_rows:
        goal = _find_marker_position(board_rows, "G")
    if goal is not None:
        state.goal_col, state.goal_row = goal

    state.blocks = _extract_blocks(response, board_rows)
    if not state.blocks and board_rows:
        inferred = _infer_blocks_from_board(board_rows)
        if inferred:
            state.blocks = inferred
            state.notes.append("blocks_inferred_from_board")

    return state


def find_possible_flag(response: dict[str, Any]) -> str | None:
    """Przeszukuje odpowiedź API pod kątem potencjalnej flagi/sukcesu.

    Args:
        response: Odpowiedź API.

    Returns:
        Tekst potencjalnej flagi lub `None`, jeśli nie znaleziono.
    """

    for value in _walk_values(response):
        if not isinstance(value, str):
            continue
        lower = value.lower()
        if "flg:" in lower or "flag" in lower or "{{" in value or "grat" in lower:
            return value
    return None


def to_serializable_state(state: BoardState) -> dict[str, Any]:
    """Konwertuje `BoardState` do formatu gotowego do zapisu JSON.

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
        "reached_goal": state.reached_goal,
        "notes": state.notes,
    }


def _extract_board_rows(payload: Any) -> list[str]:
    """Wydobywa reprezentację planszy 7x5 z różnych wariantów payloadu.

    Args:
        payload: Dowolna część odpowiedzi API.

    Returns:
        Lista 5 wierszy długości 7 lub pusta lista.
    """

    candidates = []
    for key in ("board", "map", "grid", "reactor", "state"):
        value = _deep_find_key(payload, key)
        if value is not None:
            candidates.append(value)

    if isinstance(payload, str):
        candidates.append(payload)

    for candidate in candidates:
        rows = _normalize_rows(candidate)
        if rows:
            return rows
    return []


def _normalize_rows(candidate: Any) -> list[str]:
    """Normalizuje surową strukturę planszy do listy 5 wierszy.

    Args:
        candidate: Potencjalna reprezentacja planszy.

    Returns:
        Lista wierszy długości 7 lub pusta lista.
    """

    rows: list[str] = []
    if isinstance(candidate, str):
        lines = [line.strip() for line in candidate.splitlines() if line.strip()]
        rows = [_normalize_row(line) for line in lines]
    elif isinstance(candidate, list):
        if all(isinstance(item, str) for item in candidate):
            rows = [_normalize_row(item) for item in candidate]
        elif all(isinstance(item, list) for item in candidate):
            rows = [_normalize_row("".join(str(cell) for cell in item)) for item in candidate]

    valid = [row for row in rows if len(row) == 7]
    if len(valid) >= 5:
        return valid[:5]
    return []


def _normalize_row(text: str) -> str:
    """Czyści pojedynczy wiersz planszy i ogranicza go do symboli planszy.

    Args:
        text: Surowy wiersz.

    Returns:
        Wiersz o długości do 7 znaków.
    """

    allowed = {"P", "G", "B", ".", "↑", "↓", "^", "v"}
    compact = "".join(char for char in text if char in allowed)
    compact = compact.replace("^", "↑").replace("v", "↓")
    return compact[:7]


def _extract_robot_position(payload: Any) -> GridPos | None:
    """Wydobywa pozycję robota z odpowiedzi API.

    Args:
        payload: Odpowiedź API.

    Returns:
        Pozycja `(kolumna, wiersz)` lub `None`.
    """

    for key in ("robot", "player", "position", "agent"):
        value = _deep_find_key(payload, key)
        pos = _parse_position_dict(value)
        if pos is not None:
            return pos
    return None


def _extract_goal_position(payload: Any) -> GridPos | None:
    """Wydobywa pozycję celu z odpowiedzi API.

    Args:
        payload: Odpowiedź API.

    Returns:
        Pozycja celu `(kolumna, wiersz)` lub `None`.
    """

    for key in ("goal", "target", "destination"):
        value = _deep_find_key(payload, key)
        pos = _parse_position_dict(value)
        if pos is not None:
            return pos
    return None


def _parse_position_dict(value: Any) -> GridPos | None:
    """Parsuje słownik pozycji do pary `(kolumna, wiersz)`.

    Args:
        value: Potencjalny słownik z polami pozycji.

    Returns:
        Pozycja `(kolumna, wiersz)` lub `None`.
    """

    if not isinstance(value, dict):
        return None

    col = value.get("col", value.get("column", value.get("x")))
    row = value.get("row", value.get("y"))

    if isinstance(col, int) and isinstance(row, int):
        return col, row
    return None


def _find_marker_position(rows: list[str], marker: str) -> GridPos | None:
    """Wyszukuje pozycję symbolu na planszy.

    Args:
        rows: Lista wierszy planszy.
        marker: Szukany symbol, np. `P` lub `G`.

    Returns:
        Pozycja `(kolumna, wiersz)` lub `None`.
    """

    for row_idx, row_text in enumerate(rows, start=1):
        col_idx = row_text.find(marker)
        if col_idx != -1:
            return col_idx + 1, row_idx
    return None


def _extract_blocks(payload: Any, board_rows: list[str]) -> list[Block]:
    """Wydobywa listę bloczków z odpowiedzi API.

    Args:
        payload: Odpowiedź API.
        board_rows: Znormalizowane wiersze planszy.

    Returns:
        Lista bloczków.
    """

    blocks_data = None
    for key in ("blocks", "obstacles", "reactor_blocks"):
        blocks_data = _deep_find_key(payload, key)
        if blocks_data is not None:
            break

    result: list[Block] = []
    if isinstance(blocks_data, list):
        for raw_block in blocks_data:
            parsed = _parse_block(raw_block)
            if parsed is not None:
                result.append(parsed)

    if result:
        return result

    # Fallback: infer blocks from board and optional direction overlays.
    inferred = _infer_blocks_from_board(board_rows)
    if inferred:
        return inferred
    return []


def _parse_block(raw_block: Any) -> Block | None:
    """Parsuje pojedynczy wpis bloczka do obiektu `Block`.

    Args:
        raw_block: Surowy wpis bloczka.

    Returns:
        Obiekt `Block` lub `None`, gdy dane są niepełne.
    """

    if not isinstance(raw_block, dict):
        return None

    col = raw_block.get("col", raw_block.get("column", raw_block.get("x")))
    top_row = raw_block.get("top_row", raw_block.get("row", raw_block.get("y")))
    direction_raw = raw_block.get("direction", raw_block.get("dir", "down"))

    if not isinstance(col, int) or not isinstance(top_row, int):
        return None

    direction = _normalize_direction(direction_raw)
    return Block(column=col, top_row=top_row, direction=direction)


def _infer_blocks_from_board(rows: list[str]) -> list[Block]:
    """Buduje listę bloczków na podstawie symboli `B` na planszy.

    Args:
        rows: Lista wierszy planszy.

    Returns:
        Lista oszacowanych bloczków.
    """

    blocks: list[Block] = []
    if not rows:
        return blocks

    for col in range(1, 8):
        b_rows = [row for row in range(1, 6) if rows[row - 1][col - 1] == "B"]
        if len(b_rows) < 2:
            continue

        top_row = min(b_rows)
        direction = "down"

        # Jeśli obok segmentu występuje strzałka, potraktuj ją jako wskazówkę kierunku.
        arrow_up_found = any(_neighbor_has_arrow(rows, col, row, "↑") for row in b_rows)
        arrow_down_found = any(_neighbor_has_arrow(rows, col, row, "↓") for row in b_rows)
        if arrow_up_found and not arrow_down_found:
            direction = "up"
        elif arrow_down_found and not arrow_up_found:
            direction = "down"

        blocks.append(Block(column=col, top_row=top_row, direction=direction))

    return blocks


def _neighbor_has_arrow(rows: list[str], col: int, row: int, arrow: str) -> bool:
    """Sprawdza, czy sąsiad pola zawiera wskazaną strzałkę.

    Args:
        rows: Wiersze planszy.
        col: Kolumna pola bazowego.
        row: Wiersz pola bazowego.
        arrow: Szukana strzałka (`↑` lub `↓`).

    Returns:
        `True`, jeśli strzałka występuje obok pola.
    """

    for d_col in (-1, 1):
        c = col + d_col
        if c < 1 or c > 7:
            continue
        if rows[row - 1][c - 1] == arrow:
            return True
    return False


def _normalize_direction(raw_direction: Any) -> str:
    """Normalizuje różne reprezentacje kierunku na `up` lub `down`.

    Args:
        raw_direction: Surowa wartość kierunku.

    Returns:
        Znormalizowany kierunek.
    """

    value = str(raw_direction).strip().lower()
    if value in {"up", "u", "-1", "↑", "north"}:
        return "up"
    return "down"


def _deep_find_key(payload: Any, target_key: str) -> Any:
    """Rekurencyjnie wyszukuje pierwszą wartość pod wskazanym kluczem.

    Args:
        payload: Obiekt wejściowy.
        target_key: Nazwa klucza do znalezienia.

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
    """Zwraca wszystkie wartości z dowolnie zagnieżdżonej struktury.

    Args:
        payload: Słownik, lista lub wartość atomowa.

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
