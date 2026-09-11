"""Modele danych dla misji pobocznej lekcji 5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class Position:
    """Reprezentuje pozycję na planszy.

    Atrybuty:
        row: Numer wiersza.
        col: Numer kolumny.
    """

    row: int
    col: int


@dataclass(slots=True, frozen=True)
class VehicleSpec:
    """Opisuje parametry pojazdu dostępnego w zadaniu.

    Atrybuty:
        name: Nazwa pojazdu.
        fuel_per_step: Koszt paliwa na ruch.
        food_per_step: Koszt jedzenia na ruch.
        speed: Względna prędkość.
    """

    name: str
    fuel_per_step: float
    food_per_step: float
    speed: float


@dataclass(slots=True)
class WorldState:
    """Zawiera dane potrzebne do wyznaczania tras.

    Atrybuty:
        city_name: Nazwa miasta.
        grid: Mapa 10x10.
        start: Pozycja startowa.
        goal: Pozycja celu.
        vehicles: Zasady pojazdów.
        books_notes: Notatki kontekstowe z endpointu books.
        fuel_budget: Dostępny budżet paliwa.
        food_budget: Dostępny budżet jedzenia.
    """

    city_name: str
    grid: list[list[str]]
    start: Position
    goal: Position
    vehicles: dict[str, VehicleSpec]
    books_notes: list[dict[str, Any]]
    fuel_budget: float
    food_budget: float


@dataclass(slots=True)
class RouteCandidate:
    """Reprezentuje jedną kandydacką trasę do wysyłki.

    Atrybuty:
        name: Nazwa strategii trasy.
        vehicle_name: Pojazd startowy.
        commands: Komendy ruchu do API.
        score: Wynik heurystyczny.
        metrics: Dodatkowe metryki trasy.
    """

    name: str
    vehicle_name: str
    commands: list[str]
    score: float
    metrics: dict[str, Any]

    def to_answer(self) -> list[str]:
        """Konwertuje trasę do formatu pola `answer`.

        Returns:
            Lista rozpoczynająca się od nazwy pojazdu.
        """

        return [self.vehicle_name, *self.commands]

