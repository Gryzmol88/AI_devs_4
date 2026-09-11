"""Silnik decyzji dla ruchu robota na planszy reactor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models import Block, BoardState


Command = Literal["left", "right", "wait"]


@dataclass(slots=True)
class Decision:
    """Wynik pojedynczego kroku decyzyjnego.

    Atrybuty:
        command: Wybrana komenda ruchu.
        reason: Krótkie uzasadnienie decyzji.
        safety: Informacja czy akcja była uznana za bezpieczną.
    """

    command: Command
    reason: str
    safety: bool


@dataclass(slots=True)
class ReactorDecisionEngine:
    """Podejmuje decyzje na podstawie aktualnego stanu planszy.

    Atrybuty:
        max_wait_streak: Maksymalna liczba kolejnych czekań preferowanych przez heurystykę.
    """

    max_wait_streak: int = 3

    def choose_command(self, state: BoardState, wait_streak: int) -> Decision:
        """Wybiera kolejną komendę ruchu robota.

        Args:
            state: Znormalizowany stan planszy.
            wait_streak: Licznik kolejnych komend `wait`.

        Returns:
            Obiekt `Decision` opisujący wybrany ruch.
        """

        right_safe, right_reason = self._is_command_safe(state, "right")
        wait_safe, wait_reason = self._is_command_safe(state, "wait")
        left_safe, left_reason = self._is_command_safe(state, "left")

        if right_safe:
            return Decision(command="right", reason="bezpieczny_postep_w_prawo", safety=True)

        if wait_safe and wait_streak < self.max_wait_streak:
            return Decision(command="wait", reason=f"czekanie_bezpieczne:{wait_reason}", safety=True)

        if left_safe:
            return Decision(command="left", reason=f"unik_kolizji:{left_reason}", safety=True)

        if wait_safe:
            return Decision(
                command="wait",
                reason="awaryjnie_wait_mimo_przekroczonego_streak",
                safety=True,
            )

        if left_safe:
            return Decision(command="left", reason="awaryjny_ruch_w_lewo", safety=False)

        # Brak bezpiecznej opcji; wybieramy wait jako najmniej agresywną akcję.
        return Decision(command="wait", reason="brak_bezpiecznej_akcji", safety=False)

    def _is_command_safe(self, state: BoardState, command: Command) -> tuple[bool, str]:
        """Ocena bezpieczeństwa pojedynczej komendy.

        Args:
            state: Aktualny stan planszy.
            command: Kandydat komendy do oceny.

        Returns:
            Krotka `(czy_bezpieczne, powód)`.
        """

        next_col = self._next_robot_col(state.robot_col, command)
        if next_col is None:
            return False, "ruch_poza_plansza"

        predicted_blocks = [self._predict_next_block(block) for block in state.blocks]
        occupied_next = set()
        for block in predicted_blocks:
            occupied_next.update(block.cells)

        if (next_col, state.robot_row) in occupied_next:
            return False, "kolizja_w_nastepnym_kroku"

        return True, "safe"

    def _next_robot_col(self, robot_col: int, command: Command) -> int | None:
        """Wyznacza kolumnę robota po wykonaniu komendy.

        Args:
            robot_col: Aktualna kolumna robota.
            command: Komenda ruchu.

        Returns:
            Kolumna po ruchu lub `None`, gdy ruch wykracza poza planszę.
        """

        if command == "right":
            return robot_col + 1 if robot_col < 7 else None
        if command == "left":
            return robot_col - 1 if robot_col > 1 else None
        return robot_col

    def _predict_next_block(self, block: Block) -> Block:
        """Symuluje pojedynczy krok ruchu bloczka.

        Args:
            block: Aktualny stan bloczka.

        Returns:
            Nowy stan bloczka po jednym kroku.
        """

        top_row = block.top_row
        direction = block.direction

        if direction == "up":
            if top_row <= 1:
                return Block(column=block.column, top_row=2, direction="down")
            return Block(column=block.column, top_row=top_row - 1, direction="up")

        # direction == "down"
        if top_row >= 4:
            return Block(column=block.column, top_row=3, direction="up")
        return Block(column=block.column, top_row=top_row + 1, direction="down")
