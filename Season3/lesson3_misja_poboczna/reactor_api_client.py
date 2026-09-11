"""Klient komend robota dla endpointu `/verify` zadania reactor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from config import Settings
from http_utils import post_json_with_retries


Command = Literal["start", "left", "right", "wait"]


@dataclass(slots=True)
class ReactorApiClient:
    """Obsługuje wysyłkę pojedynczych komend robota.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def send_command(self, command: Command) -> dict[str, Any]:
        """Wysyła komendę do API i zwraca odpowiedź JSON.

        Args:
            command: Komenda sterująca robotem.

        Returns:
            Odpowiedź API jako słownik.
        """

        payload = {
            "apikey": self.settings.hub_api_key,
            "task": self.settings.reactor_task_name,
            "answer": {"command": command},
        }
        return post_json_with_retries(
            url=self.settings.hub_verify_url,
            payload=payload,
            timeout_seconds=self.settings.request_timeout_seconds,
            retry_limit=self.settings.retry_limit,
            backoff_base_seconds=self.settings.backoff_base_seconds,
            headers=None,
        )
