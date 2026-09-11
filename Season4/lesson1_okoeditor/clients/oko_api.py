"""Klient komunikacji z API centrali zadania `okoeditor`."""

from typing import Any

import requests

from config import AppSettings
from models.schemas import VerifyRequest


class OkoApiClient:
    """Obsługuje wywołania endpointu `/verify`.

    Args:
        settings: Konfiguracja aplikacji z danymi API.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta API.

        Args:
            settings: Obiekt konfiguracji aplikacji.
        """

        self._settings = settings

    def call_verify(self, answer: dict[str, Any]) -> dict[str, Any]:
        """Wysyła żądanie do `/verify` z przekazaną akcją.

        Args:
            answer: Słownik zawierający akcję i parametry.

        Returns:
            Odpowiedź API w postaci słownika.

        Raises:
            RuntimeError: Gdy API zwróci błąd HTTP.
        """

        payload = VerifyRequest(
            apikey=self._settings.aidevs_api_key,
            task=self._settings.aidevs_task,
            answer=answer,
        )

        response = requests.post(
            self._settings.aidevs_verify_url,
            json=payload.model_dump(),
            timeout=self._settings.app_timeout_seconds,
        )

        if not response.ok:
            error_details: Any
            try:
                error_details = response.json()
            except ValueError:
                error_details = response.text
            raise RuntimeError(
                f"API verify error {response.status_code}: {error_details}"
            )

        return response.json()

    def help(self) -> dict[str, Any]:
        """Pobiera opis dostępnych akcji API.

        Returns:
            Słownik zawierający odpowiedź API dla akcji `help`.
        """

        return self.call_verify({"action": "help"})

    def done(self) -> dict[str, Any]:
        """Zgłasza zakończenie zadania.

        Returns:
            Słownik zawierający odpowiedź API dla akcji `done`.
        """

        return self.call_verify({"action": "done"})
