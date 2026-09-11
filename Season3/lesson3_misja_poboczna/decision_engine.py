"""Silnik decyzji ruchu robota dla scenariusza "tam i z powrotem"."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models import Block, BoardState


Command = Literal["left", "right", "wait"]


@dataclass(slots=True)
class Decision:
    """Opis decyzji ruchu robota.

    Atrybuty:
        command: Wybrana komenda.
        reason: Krótkie uzasadnienie decyzji.
        safe: Informacja czy akcja jest uznana za bezpieczną.
    """

    command: Command
    reason: str
    safe: bool


@dataclass(slots=True)
class ThereAndBackEngine:
    """Heurystyczny silnik ruchu robota.

    Atrybuty:
        max_wait_streak: Preferowany limit kolejnych komend `wait`.
    """

    max_wait_streak: int = 3

    def choose(self, state: BoardState, target_col: int, wait_streak: int) -> Decision:
        """Wybiera kolejny ruch do wskazanej kolumny docelowej.

        Args:
            state: Aktualny stan planszy.
            target_col: Kolumna, do której robot powinien zmierzać.
            wait_streak: Liczba kolejnych komend `wait`.

        Returns:
            Obiekt `Decision` opisujący wybrany ruch.
        """

        preferred = "right" if state.robot_col < target_col else "left"
        opposite = "left" if preferred == "right" else "right"

        preferred_safe, preferred_reason = self._is_safe(state, preferred)
        wait_safe, wait_reason = self._is_safe(state, "wait")
        opposite_safe, opposite_reason = self._is_safe(state, opposite)

        if preferred_safe:
            return Decision(command=preferred, reason=f"postep:{preferred_reason}", safe=True)

        if wait_safe and wait_streak < self.max_wait_streak:
            return Decision(command="wait", reason=f"bezpieczne_czekanie:{wait_reason}", safe=True)

        if opposite_safe:
            return Decision(command=opposite, reason=f"unik:{opposite_reason}", safe=True)

        if wait_safe:
            return Decision(command="wait", reason="awaryjny_wait", safe=True)

        return Decision(command=opposite, reason="awaryjny_ruch", safe=False)

    def _is_safe(self, state: BoardState, command: Command) -> tuple[bool, str]:
        """Sprawdza bezpieczeństwo komendy w kolejnym kroku.

        Args:
            state: Aktualny stan planszy.
            command: Sprawdzana komenda.

        Returns:
            Krotka `(bezpiecznie, powod)`.
        """

        next_col = self._next_col(state.robot_col, command)
        if next_col is None:
            return False, "poza_plansza"

        predicted = [self._predict_block(block) for block in state.blocks]
        occupied = set()
        for block in predicted:
            occupied.update(block.cells)

        if (next_col, state.robot_row) in occupied:
            return False, "kolizja"

        return True, "ok"

    def _next_col(self, current_col: int, command: Command) -> int | None:
        """Wyznacza kolumnę robota po wykonaniu komendy.

        Args:
            current_col: Aktualna kolumna robota.
            command: Komenda ruchu.

        Returns:
            Kolumna po ruchu albo `None`, gdy ruch wyjdzie poza planszę.
        """

        if command == "right":
            return current_col + 1 if current_col < 7 else None
        if command == "left":
            return current_col - 1 if current_col > 1 else None
        return current_col

    def _predict_block(self, block: Block) -> Block:
        """Symuluje jeden krok ruchu pojedynczego bloku.

        Args:
            block: Aktualny blok.

        Returns:
            Blok po jednym kroku symulacji.
        """

        if block.direction == "up":
            if block.top_row <= 1:
                return Block(column=block.column, top_row=2, direction="down")
            return Block(column=block.column, top_row=block.top_row - 1, direction="up")

        if block.top_row >= 4:
            return Block(column=block.column, top_row=3, direction="up")
        return Block(column=block.column, top_row=block.top_row + 1, direction="down")
