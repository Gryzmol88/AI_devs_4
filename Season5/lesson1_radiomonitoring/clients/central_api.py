"""Klient HTTP do komunikacji z Centralą zadania radiomonitoring."""

from __future__ import annotations

from typing import Any

import requests

from config import Settings
from models import CentralaRequest, ListenResponse


class CentralaApiClient:
    """Obsługuje komunikację z endpointem /verify."""

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klienta Centrali.

        Args:
            settings: Obiekt konfiguracyjny aplikacji.
        """
        self._settings = settings
        self._url = f"{settings.centrala_base_url.rstrip('/')}/verify"

    def send_action(self, action_payload: dict[str, Any]) -> dict[str, Any]:
        """Wysyła dowolną akcję do Centrali.

        Args:
            action_payload: Obiekt answer zawierający parametry akcji.

        Returns:
            Zdeserializowaną odpowiedź JSON.

        Raises:
            requests.HTTPError: Gdy serwer zwróci błąd HTTP.
        """
        payload = CentralaRequest(
            apikey=self._settings.centrala_api_key,
            task=self._settings.task_name,
            answer=action_payload,
        )
        response = requests.post(
            self._url,
            json=payload.model_dump(),
            timeout=self._settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def start_session(self) -> dict[str, Any]:
        """Uruchamia sesję nasłuchu po stronie Centrali.

        Returns:
            Odpowiedź JSON po akcji start.
        """
        return self.send_action({"action": "start"})

    def listen(self) -> ListenResponse:
        """Pobiera kolejną porcję sygnału radiowego.

        Returns:
            Odpowiedź nasłuchu zmapowaną do modelu ListenResponse.
        """
        raw_response = self.send_action({"action": "listen"})
        return ListenResponse.model_validate(raw_response)

    def transmit(self, report_payload: dict[str, Any]) -> dict[str, Any]:
        """Wysyła raport końcowy do Centrali.

        Args:
            report_payload: Finalny obiekt answer z action=transmit.

        Returns:
            Odpowiedź JSON z weryfikacji.
        """
        return self.send_action(report_payload)
