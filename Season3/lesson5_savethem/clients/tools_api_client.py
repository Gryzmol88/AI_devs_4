"""Klient HTTP do komunikacji z narzędziami huba i endpointem `/verify`."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urljoin
from dataclasses import dataclass
from typing import Any

from config import Settings


@dataclass(slots=True)
class ToolsApiClient:
    """Obsługuje komunikację z `toolsearch`, narzędziami i `/verify`.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def toolsearch(self, query: str) -> dict[str, Any]:
        """Wysyła zapytanie do `toolsearch`.

        Args:
            query: Zapytanie opisujące potrzebną wiedzę o narzędziach.

        Returns:
            Payload JSON zwrócony przez `toolsearch`.
        """

        return self._post_json(self.settings.toolsearch_url, {"apikey": self.settings.hub_api_key, "query": query})

    def tool_query(self, endpoint_url: str, query: str) -> dict[str, Any]:
        """Wysyła zapytanie do konkretnego narzędzia wykrytego przez discovery.

        Args:
            endpoint_url: URL narzędzia.
            query: Zapytanie w języku angielskim.

        Returns:
            Payload JSON zwrócony przez narzędzie.
        """

        resolved_url = self._resolve_url(endpoint_url)
        return self._post_json(resolved_url, {"apikey": self.settings.hub_api_key, "query": query})

    def _resolve_url(self, endpoint_url: str) -> str:
        """Zamienia URL względny narzędzia na pełny adres endpointu.

        Args:
            endpoint_url: URL absolutny lub względny.

        Returns:
            Pełny URL gotowy do wywołania HTTP.
        """

        stripped = endpoint_url.strip()
        if stripped.startswith("http://") or stripped.startswith("https://"):
            return stripped
        return urljoin(self.settings.toolsearch_url, stripped)

    def verify(self, answer: list[str]) -> dict[str, Any]:
        """Wysyła finalną odpowiedź do endpointu weryfikacyjnego.

        Args:
            answer: Tablica odpowiedzi w formacie wymaganym przez zadanie.

        Returns:
            Payload JSON zwrócony przez `/verify`.
        """

        payload = {
            "apikey": self.settings.hub_api_key,
            "task": self.settings.savethem_task_name,
            "answer": answer,
        }
        return self._post_json(self.settings.verify_url, payload)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Wysyła żądanie POST JSON i zwraca sparsowaną odpowiedź.

        Args:
            url: URL endpointu.
            payload: Słownik wysyłany jako JSON.

        Returns:
            Odpowiedź endpointu jako słownik.

        Raises:
            RuntimeError: Gdy endpoint zwróci błąd HTTP lub nieprawidłowy JSON.
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
