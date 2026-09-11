"""Klient API dla zadania reactor wysyłający komendy do /verify."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from config import Settings
from http_utils import post_json_with_retries


Command = Literal["start", "left", "right", "wait"]


@dataclass(slots=True)
class ReactorApiClient:
    """Obsługuje wysyłkę komend sterujących robotem.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def send_command(self, command: Command) -> dict[str, Any]:
        """Wysyła pojedynczą komendę do endpointu `/verify`.

        Args:
            command: Komenda sterująca robotem.

        Returns:
            Odpowiedź endpointu jako słownik.
        """

        payload = {
            "apikey": self.settings.hub_api_key,
            "task": self.settings.task_name,
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
