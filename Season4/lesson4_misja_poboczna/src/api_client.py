"""Klient HTTP do komunikacji z API verify."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from .config import AppSettings


class VerifyApiClient:
    """Obsługuje wywołania endpointu verify dla taska pobocznego."""

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta API.

        Args:
            settings: Ustawienia aplikacji.
        """

        self._settings = settings
        self._session = requests.Session()

    @staticmethod
    def _iso_now() -> str:
        """Zwraca aktualny czas ISO.

        Returns:
            str: Czas lokalny w ISO z milisekundami.
        """

        return datetime.now().isoformat(timespec="milliseconds")

    def call(self, answer: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Wysyła request do verify i zwraca `(response, trace)`.

        Args:
            answer: Pole `answer` zgodne z API.

        Returns:
            tuple[dict[str, Any], dict[str, Any]]: Odpowiedź API i ślad wywołania.
        """

        request_payload = {
            "apikey": self._settings.ag3nts_api_key,
            "task": self._settings.task_name,
            "answer": answer,
        }

        started_at = self._iso_now()
        response = self._session.post(
            self._settings.ag3nts_verify_url,
            json=request_payload,
            timeout=self._settings.request_timeout_seconds,
        )
        finished_at = self._iso_now()

        try:
            response_payload: dict[str, Any] = response.json()
        except ValueError:
            response_payload = {"rawText": response.text}

        trace = {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "http": {"statusCode": response.status_code, "ok": response.ok},
            "request": {"task": self._settings.task_name, "answer": answer},
            "response": response_payload,
        }

        if not response.ok:
            details = response.text.strip()
            raise requests.HTTPError(
                f"{response.status_code} HTTP error for {response.url}. API details: {details}",
                response=response,
            )

        return response_payload, trace

