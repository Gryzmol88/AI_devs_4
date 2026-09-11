"""Klient HTTP do komunikacji z centralą zadania phonecall."""

from __future__ import annotations

from typing import Any

import requests

from config import Settings
from models import HubResponse


class HubClient:
    """Obsługuje komunikację z endpointem weryfikacji zadania.

    Args:
        settings: Konfiguracja aplikacji zawierająca klucze i endpointy.
    """

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klienta API centrali."""

        self._settings = settings

    def start_call(self) -> HubResponse:
        """Rozpoczyna sesję rozmowy z operatorem.

        Returns:
            HubResponse: Odpowiedź API po akcji `start`.
        """

        payload = {
            "apikey": self._settings.aidevs_api_key.get_secret_value(),
            "task": "phonecall",
            "answer": {"action": "start"},
        }
        raw = self._post(payload)
        return self._normalize(raw)

    def send_audio(self, audio_base64: str) -> HubResponse:
        """Wysyła pojedynczą wiadomość audio zakodowaną base64.

        Args:
            audio_base64: Treść nagrania MP3 zakodowana base64.

        Returns:
            HubResponse: Odpowiedź API na wysłane nagranie.
        """

        payload = {
            "apikey": self._settings.aidevs_api_key.get_secret_value(),
            "task": "phonecall",
            "answer": {"audio": audio_base64},
        }
        raw = self._post(payload)
        return self._normalize(raw)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Wysyła żądanie POST do centrali.

        Args:
            payload: Dane JSON przekazywane do endpointu.

        Returns:
            dict[str, Any]: Zdekodowana odpowiedź JSON.

        Raises:
            requests.HTTPError: Gdy endpoint zwróci błąd HTTP.
        """

        response = requests.post(
            self._settings.aidevs_verify_url,
            json=payload,
            timeout=self._settings.request_timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}. Response body: {response.text[:1000]}",
                response=response,
            ) from exc
        return response.json()

    def _normalize(self, raw: dict[str, Any]) -> HubResponse:
        """Normalizuje różne formaty odpowiedzi do wspólnego modelu.

        Args:
            raw: Oryginalna odpowiedź API.

        Returns:
            HubResponse: Ujednolicona postać odpowiedzi.
        """

        text = None
        audio_base64 = None

        if isinstance(raw.get("message"), str):
            text = raw["message"]
        if isinstance(raw.get("text"), str):
            text = raw["text"]
        if isinstance(raw.get("audio"), str):
            audio_base64 = raw["audio"]
        if isinstance(raw.get("answer"), dict):
            text = raw["answer"].get("text", text)
            audio_base64 = raw["answer"].get("audio", audio_base64)

        done_markers = ("flag", "correct", "success")
        done = any(marker in raw for marker in done_markers)

        return HubResponse(raw=raw, text=text, audio_base64=audio_base64, done=done)
