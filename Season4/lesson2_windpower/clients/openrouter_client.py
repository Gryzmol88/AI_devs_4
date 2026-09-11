"""Opcjonalny klient OpenRouter do wsparcia analizy."""

from __future__ import annotations

from typing import Any

import requests

from config import AppSettings


class OpenRouterClient:
    """Udostepnia minimalne wywolanie chat completions OpenRouter."""

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta OpenRouter.

        Args:
            settings: Konfiguracja aplikacji.
        """

        self._settings = settings
        self._session = requests.Session()

    def is_enabled(self) -> bool:
        """Sprawdza, czy wsparcie OpenRouter jest aktywne.

        Returns:
            True, jesli wlaczono flage oraz podano klucz API.
        """

        return self._settings.app_use_llm_assist and bool(self._settings.openrouter_api_key)

    def analyze_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        """Wykonuje pomocnicza analize JSON przez model OpenRouter.

        Args:
            system_prompt: Instrukcja systemowa modelu.
            user_payload: Dane uzytkownika przekazywane do modelu.

        Returns:
            Odpowiedz API OpenRouter jako slownik.
        """

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._settings.openrouter_site_url,
            "X-Title": self._settings.openrouter_app_name,
        }
        payload = {
            "model": self._settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(user_payload)},
            ],
            "response_format": {"type": "json_object"},
        }
        response = self._session.post(
            f"{self._settings.openrouter_base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self._settings.app_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
