"""Modele domenowe wykorzystywane przez solver zadania domatowo."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Unit:
    """Przechowuje dane o jednostce poruszającej się po mapie.

    Attributes:
        unit_id: Identyfikator jednostki zwrócony przez API.
        unit_type: Typ jednostki, np. `scout` lub `transporter`.
        position: Aktualna pozycja jednostki w formacie planszy, np. `F6`.
        passengers: Lista identyfikatorów przewożonych zwiadowców.
    """

    unit_id: str
    unit_type: str
    position: str
    passengers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MissionState:
    """Przechowuje bieżący stan misji, jednostek i przebiegu operacji.

    Attributes:
        action_points_left: Liczba pozostałych punktów akcji.
        units: Słownik jednostek po ich identyfikatorze.
        mission_trace: Historia działań i decyzji zapisywana do pliku.
        target_found: Flaga informująca, czy odnaleziono partyzanta.
        target_position: Pole, na którym potwierdzono obecność partyzanta.
    """

    action_points_left: int = 300
    units: dict[str, Unit] = field(default_factory=dict)
    mission_trace: list[dict[str, Any]] = field(default_factory=list)
    target_found: bool = False
    target_position: str = ""

    def add_trace(self, step: str, payload: dict[str, Any]) -> None:
        """Dodaje wpis śladu wykonania operacji.

        Args:
            step: Nazwa kroku lub etapu procesu.
            payload: Dane związane z danym krokiem.

        Returns:
            None: Funkcja modyfikuje wewnętrzną listę `mission_trace`.

        Effects:
            Dopisuje nowy rekord do historii przebiegu.
        """

        self.mission_trace.append({"step": step, "payload": payload})


@dataclass(slots=True)
class PlanResult:
    """Reprezentuje rezultat planowania przeszukania mapy.

    Attributes:
        preferred_cells: Lista pól mapy sugerowanych do priorytetowego sprawdzenia.
        notes: Komentarz tekstowy wyjaśniający logikę priorytetyzacji.
    """

    preferred_cells: list[str]
    notes: str

