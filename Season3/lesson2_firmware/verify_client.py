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

    def submit_confirmation(self, confirmation_code: str) -> dict[str, Any]:
        """Wysyła końcową odpowiedź do zadania `firmware`.

        Args:
            confirmation_code: Kod w formacie `ECCS-...`.

        Returns:
            Odpowiedź endpointu verify jako słownik.
        """

        payload = {
            "apikey": self.settings.hub_api_key,
            "task": "firmware",
            "answer": {"confirmation": confirmation_code},
        }
        return post_json_with_retries(
            url=self.settings.hub_verify_url,
            payload=payload,
            headers=None,
            timeout_seconds=self.settings.request_timeout_seconds,
            retry_limit=self.settings.retry_limit,
            backoff_base_seconds=self.settings.backoff_base_seconds,
        )

