"""Klient do komunikacji z API powłoki w zadaniu firmware."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from config import Settings
from http_utils import HttpRequestError, post_json_with_retries


@dataclass(slots=True)
class ShellApiClient:
    """Obsługuje wysyłanie komend do zdalnego shell API.

    Atrybuty:
        settings: Ustawienia aplikacji.
    """

    settings: Settings

    def _extract_error_payload(self, raw_error: str) -> dict[str, Any]:
        """Wyciąga JSON błędu z surowego komunikatu wyjątku HTTP.

        Args:
            raw_error: Pełny tekst błędu.

        Returns:
            Słownik z danymi błędu API lub pusty słownik.
        """

        json_start = raw_error.find("{")
        if json_start == -1:
            return {}
        try:
            parsed = json.loads(raw_error[json_start:])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def run_command(self, command: str) -> dict[str, Any]:
        """Wysyła pojedynczą komendę do shell API.

        Args:
            command: Komenda do wykonania w maszynie wirtualnej.

        Returns:
            Ustandaryzowany wynik narzędzia shell zawierający:
            - `ok`: czy komenda zakończyła się odpowiedzią 2xx
            - `response`: treść odpowiedzi API przy sukcesie
            - `http_status`: kod HTTP przy błędzie
            - `error_message`: opis błędu przy niepowodzeniu
            - `is_retryable`: czy błąd kwalifikuje się do ponawiania
        """

        payload = {"apikey": self.settings.hub_api_key, "cmd": command}
        try:
            response = post_json_with_retries(
                url=self.settings.hub_shell_url,
                payload=payload,
                headers=None,
                timeout_seconds=self.settings.request_timeout_seconds,
                retry_limit=self.settings.retry_limit,
                backoff_base_seconds=self.settings.backoff_base_seconds,
            )
            return {"ok": True, "response": response}
        except HttpRequestError as error:
            retryable_statuses = {408, 425, 429, 500, 502, 503, 504}
            payload = self._extract_error_payload(str(error))
            error_code = payload.get("code")
            ban_data = payload.get("ban") if isinstance(payload.get("ban"), dict) else None
            is_ban = bool(error_code in {-733, -735} or ban_data)
            return {
                "ok": False,
                "http_status": error.status_code,
                "error_message": str(error),
                "is_retryable": error.status_code in retryable_statuses
                if error.status_code is not None
                else True,
                "error_code": error_code,
                "ban": ban_data,
                "is_ban": is_ban,
            }
