"""Operacje wejścia/wyjścia na artefaktach uruchomienia aplikacji."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class OutputWriter:
    """Zarządza zapisem plików diagnostycznych w katalogu `output`.

    Atrybuty:
        base_dir: Bazowy katalog na artefakty.
        session_dir: Katalog bieżącej sesji.
        step_index: Licznik kolejnych kroków zapisu.
    """

    def __init__(self, base_dir: Path) -> None:
        """Tworzy writer i przygotowuje katalog sesji.

        Args:
            base_dir: Bazowy katalog `output`.
        """

        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        session_name = datetime.now(UTC).strftime("session_%Y%m%dT%H%M%SZ")
        self.session_dir = self.base_dir / session_name
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.step_index = 0

    def write_json(self, label: str, payload: dict[str, Any]) -> Path:
        """Zapisuje obiekt JSON jako kolejny krok sesji.

        Args:
            label: Etykieta kroku umieszczana w nazwie pliku.
            payload: Treść dokumentu JSON.

        Returns:
            Ścieżka utworzonego pliku.
        """

        safe_label = self._sanitize_label(label)
        filename = f"step{self.step_index:03d}_{safe_label}.json"
        self.step_index += 1
        path = self.session_dir / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_text(self, filename: str, content: str) -> Path:
        """Zapisuje plik tekstowy w katalogu sesji.

        Args:
            filename: Nazwa pliku wynikowego.
            content: Treść do zapisania.

        Returns:
            Ścieżka utworzonego pliku.
        """

        path = self.session_dir / self._sanitize_label(filename)
        path.write_text(content, encoding="utf-8")
        return path

    def _sanitize_label(self, label: str) -> str:
        """Czyści etykietę do bezpiecznej postaci nazwy pliku.

        Args:
            label: Oryginalna etykieta.

        Returns:
            Etykieta zawierająca jedynie bezpieczne znaki.
        """

        cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in label.strip())
        return cleaned or "artifact"

