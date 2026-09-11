"""Modele danych dla przeplywu zadania windpower."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ConfigPoint:
    """Opisuje pojedynczy punkt konfiguracji turbiny.

    Atrybuty:
        timestamp: Znacznik czasu konfiguracji w formacie YYYY-MM-DD HH:00:00.
        wind_ms: Predkosc wiatru dla godziny konfiguracji.
        pitch_angle: Kat lopat wirnika.
        turbine_mode: Tryb pracy turbiny, np. idle lub production.
        reason: Powod dodania punktu harmonogramu.
    """

    timestamp: datetime
    wind_ms: float
    pitch_angle: int
    turbine_mode: str
    reason: str

    def as_payload_key(self) -> str:
        """Zwraca znacznik czasu jako klucz slownika configs.

        Returns:
            Data i godzina w formacie YYYY-MM-DD HH:MM:SS.
        """

        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")


@dataclass(slots=True)
class WindDataPoint:
    """Reprezentuje pojedynczy rekord prognozy pogody.

    Atrybuty:
        timestamp: Znacznik czasu pomiaru/prognozy.
        wind_speed: Predkosc wiatru.
        raw: Oryginalny rekord wejsciowy z API.
    """

    timestamp: datetime
    wind_speed: float
    raw: dict[str, Any]


@dataclass(slots=True)
class PlanningContext:
    """Agreguje dane potrzebne do wyliczenia harmonogramu.

    Atrybuty:
        weather_points: Lista punktow prognozy.
        turbine_wind_limit: Maksymalna bezpieczna predkosc wiatru.
        missing_power: Brakujaca moc do wyprodukowania.
    """

    weather_points: list[WindDataPoint]
    turbine_wind_limit: float
    missing_power: float


@dataclass(slots=True)
class PlanningResult:
    """Wynik planowania konfiguracji.

    Atrybuty:
        configs: Posortowana lista punktow harmonogramu.
        production_point: Punkt konfiguracji uruchamiajacy produkcje.
        notes: Dodatkowe uwagi diagnostyczne.
    """

    configs: list[ConfigPoint]
    production_point: ConfigPoint
    notes: list[str]
