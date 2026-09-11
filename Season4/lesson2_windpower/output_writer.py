"""Zapis artefaktow uruchomienia do katalogu output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models.schemas import PlanningResult
from utils.io import write_json
from utils.io import write_text


class OutputWriter:
    """Ulatwia zapis krokow posrednich i wyniku finalnego."""

    def __init__(self, output_dir: Path) -> None:
        """Inicjalizuje writer dla jednego uruchomienia.

        Args:
            output_dir: Katalog output biezacego uruchomienia.
        """

        self._output_dir = output_dir

    def save_json(self, filename: str, payload: Any) -> None:
        """Zapisuje dowolny plik JSON.

        Args:
            filename: Nazwa pliku w katalogu output.
            payload: Dane serializowalne do JSON.

        Side Effects:
            Tworzy lub nadpisuje plik JSON.
        """

        write_json(self._output_dir / filename, payload)

    def save_planning_result(self, filename: str, planning_result: PlanningResult) -> None:
        """Zapisuje wynik planowania w postaci JSON.

        Args:
            filename: Nazwa pliku.
            planning_result: Wynik planera.

        Side Effects:
            Tworzy lub nadpisuje plik JSON.
        """

        payload = {
            "configs": [
                {
                    "timestamp": item.as_payload_key(),
                    "wind_ms": item.wind_ms,
                    "pitch_angle": item.pitch_angle,
                    "turbine_mode": item.turbine_mode,
                    "reason": item.reason,
                }
                for item in planning_result.configs
            ],
            "production_point": {
                "timestamp": planning_result.production_point.as_payload_key(),
                "wind_ms": planning_result.production_point.wind_ms,
                "pitch_angle": planning_result.production_point.pitch_angle,
                "turbine_mode": planning_result.production_point.turbine_mode,
                "reason": planning_result.production_point.reason,
            },
            "notes": planning_result.notes,
        }
        write_json(self._output_dir / filename, payload)

    def save_text(self, filename: str, content: str) -> None:
        """Zapisuje plik tekstowy.

        Args:
            filename: Nazwa pliku.
            content: Tresc pliku.

        Side Effects:
            Tworzy lub nadpisuje plik tekstowy.
        """

        write_text(self._output_dir / filename, content)
