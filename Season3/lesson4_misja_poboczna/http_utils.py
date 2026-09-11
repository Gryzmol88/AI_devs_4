"""Niskopoziomowe narzędzia HTTP dla komunikacji z `/verify` i źródłami CSV."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class HttpRequestError(RuntimeError):
    """Sygnalizuje błąd HTTP lub problem transportowy."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Tworzy wyjątek HTTP.

        Args:
            message: Komunikat błędu.
            status_code: Kod HTTP, jeśli dostępny.
        """

        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class JsonHttpClient:
    """Uproszczony klient HTTP operujący na JSON.

    Atrybuty:
        timeout_seconds: Timeout pojedynczego żądania.
    """

    timeout_seconds: float = 30.0

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Wysyła żądanie POST JSON i zwraca odpowiedź jako słownik.

        Args:
            url: Adres docelowy.
            payload: Dane JSON wysyłane w body.

        Returns:
            Odpowiedź JSON jako słownik.

        Raises:
            HttpRequestError: Gdy żądanie kończy się błędem lub odpowiedź nie jest JSON-em.
        """

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8", errors="replace")
                return json.loads(text)
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise HttpRequestError(f"HTTP {error.code}: {details}", status_code=error.code) from error
        except urllib.error.URLError as error:
            raise HttpRequestError(f"Błąd połączenia: {error}") from error
        except json.JSONDecodeError as error:
            raise HttpRequestError(f"Niepoprawny JSON w odpowiedzi: {error}") from error

    def get_text(self, url: str) -> str:
        """Pobiera treść tekstową z podanego URL.

        Args:
            url: Adres zasobu.

        Returns:
            Treść odpowiedzi jako tekst.

        Raises:
            HttpRequestError: Gdy pobranie kończy się błędem.
        """

        request = urllib.request.Request(url=url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8-sig", errors="replace")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise HttpRequestError(f"HTTP {error.code}: {details}", status_code=error.code) from error
        except urllib.error.URLError as error:
            raise HttpRequestError(f"Błąd połączenia: {error}") from error

