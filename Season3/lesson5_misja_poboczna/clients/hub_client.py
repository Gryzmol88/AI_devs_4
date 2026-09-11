"""Klient API huba dla misji pobocznej."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from config import Settings


@dataclass(slots=True)
class HubClient:
    """Obsługuje komunikację z endpointami huba.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def fetch_map(self, city_name: str) -> dict[str, Any]:
        """Pobiera mapę miasta.

        Args:
            city_name: Nazwa miasta.

        Returns:
            Odpowiedź JSON endpointu map.
        """

        return self._post_json(self.settings.maps_url, {"apikey": self.settings.hub_api_key, "query": city_name})

    def fetch_vehicle(self, vehicle_name: str) -> dict[str, Any]:
        """Pobiera parametry konkretnego pojazdu.

        Args:
            vehicle_name: Nazwa pojazdu (`rocket`, `horse`, `walk`, `car`).

        Returns:
            Odpowiedź JSON endpointu pojazdów.
        """

        return self._post_json(
            self.settings.vehicles_url,
            {"apikey": self.settings.hub_api_key, "query": vehicle_name},
        )

    def fetch_books(self, query: str) -> dict[str, Any]:
        """Wykonuje zapytanie do endpointu notatek.

        Args:
            query: Treść zapytania.

        Returns:
            Odpowiedź JSON endpointu books.
        """

        return self._post_json(self.settings.books_url, {"apikey": self.settings.hub_api_key, "query": query})

    def verify(self, task_name: str, answer: list[str]) -> dict[str, Any]:
        """Wysyła kandydacką odpowiedź do `/verify`.

        Args:
            task_name: Nazwa taska.
            answer: Odpowiedź w formacie listy kroków.

        Returns:
            Odpowiedź JSON endpointu verify.
        """

        return self._post_json(
            self.settings.verify_url,
            {"apikey": self.settings.hub_api_key, "task": task_name, "answer": answer},
        )

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Wysyła żądanie HTTP POST i zwraca JSON.

        Args:
            url: URL endpointu.
            payload: Payload JSON.

        Returns:
            Odpowiedź endpointu jako słownik.

        Raises:
            RuntimeError: Gdy endpoint zwróci błąd HTTP lub niepoprawny JSON.
        """

        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {error.code} for {url}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Connection error for {url}: {error}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid JSON response from {url}: {error}") from error

