"""Klient do wysyłki odpowiedzi końcowej do endpointu verify."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import Settings
from http_utils import post_json_with_retries


@dataclass(slots=True)
class VerifyClient:
    """Obsługuje wysyłanie kodu potwierdzającego do huba.

    Atrybuty:
        settings: Ustawienia aplikacji.
    """

    settings: Settings

    def submit_answer(self, answer_value: str) -> dict[str, Any]:
        """Wysyła końcową odpowiedź do zadania pobocznego.

        Args:
            answer_value: Wartość odpowiedzi wykryta podczas działania.

        Returns:
            Odpowiedź endpointu verify jako słownik.
        """

        payload = {
            "apikey": self.settings.hub_api_key,
            "task": self.settings.side_task_name,
            "answer": {self.settings.side_task_answer_key: answer_value},
        }
        return post_json_with_retries(
            url=self.settings.hub_verify_url,
            payload=payload,
            headers=None,
            timeout_seconds=self.settings.request_timeout_seconds,
            retry_limit=self.settings.retry_limit,
            backoff_base_seconds=self.settings.backoff_base_seconds,
        )
