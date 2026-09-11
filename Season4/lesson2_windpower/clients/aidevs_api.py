"""Klient API dla endpointu verify zadania windpower."""

from __future__ import annotations

import time
from typing import Any

import requests

from config import AppSettings


class AIDevsApiClient:
    """Obsluguje komunikacje z API zadania windpower.

    Metody klasy enkapsuluja format payloadu wymagany przez endpoint verify.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta API.

        Args:
            settings: Konfiguracja aplikacji.
        """

        self._settings = settings
        self._session = requests.Session()

    def call(self, answer: dict[str, Any]) -> dict[str, Any]:
        """Wysyla pojedyncze zadanie do API.

        Args:
            answer: Slownik pola `answer` zgodny z dokumentacja zadania.

        Returns:
            Zdekodowana odpowiedz JSON.

        Raises:
            requests.HTTPError: Gdy endpoint zwroci blad HTTP.
            ValueError: Gdy odpowiedz nie jest JSON.
        """

        payload = {
            "apikey": self._settings.aidevs_api_key,
            "task": self._settings.aidevs_task,
            "answer": answer,
        }
        response = self._session.post(
            self._settings.aidevs_verify_url,
            json=payload,
            timeout=self._settings.app_timeout_seconds,
        )
        if not response.ok:
            details = response.text.strip()
            raise requests.HTTPError(
                f"{response.status_code} HTTP error for {response.url}. API details: {details}",
                response=response,
            )
        return response.json()

    def help(self) -> dict[str, Any]:
        """Pobiera opis dostepnych akcji zadania.

        Returns:
            Odpowiedz API dla akcji `help`.
        """

        last_error: Exception | None = None
        for _ in range(3):
            try:
                return self.call({"action": "help"})
            except requests.HTTPError as exc:
                last_error = exc
                time.sleep(0.35)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Nieoczekiwany blad podczas wywolania help.")

    def start(self) -> dict[str, Any]:
        """Uruchamia okno serwisowe zadania.

        Returns:
            Odpowiedz API dla akcji `start`.
        """

        return self.call({"action": "start"})

    def get(self, param: str) -> dict[str, Any]:
        """Zleca pobranie danych dla wskazanego parametru.

        Args:
            param: Nazwa parametru, np. weather lub powerplantcheck.

        Returns:
            Odpowiedz API dla akcji `get`.
        """

        return self.call({"action": "get", "param": param})

    def get_result(self) -> dict[str, Any]:
        """Pobiera pojedynczy gotowy wynik z kolejki API.

        Returns:
            Odpowiedz API dla akcji `getResult`.
        """

        return self.call({"action": "getResult"})

    def done(self) -> dict[str, Any]:
        """Wysyla finalna walidacje konfiguracji.

        Returns:
            Odpowiedz API dla akcji `done`.
        """

        return self.call({"action": "done"})
