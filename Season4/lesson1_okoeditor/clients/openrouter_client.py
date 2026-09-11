"""Klient integracji z API OpenRouter."""

from typing import Any

import requests

from config import AppSettings


class OpenRouterClient:
    """Zapewnia prosty interfejs do wywołań modelu przez OpenRouter.

    Args:
        settings: Konfiguracja aplikacji.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta OpenRouter.

        Args:
            settings: Obiekt konfiguracji aplikacji.
        """

        self._settings = settings

    def is_enabled(self) -> bool:
        """Sprawdza, czy klient OpenRouter może wykonywać zapytania.

        Returns:
            `True`, jeśli klucz API jest ustawiony; w przeciwnym razie `False`.
        """

        return bool(self._settings.openrouter_api_key.strip())

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> dict[str, Any]:
        """Wysyła zapytanie chat completion do OpenRouter.

        Args:
            messages: Lista wiadomości w formacie zgodnym z API chat.
            temperature: Parametr kreatywności modelu.
            max_tokens: Maksymalna liczba tokenów odpowiedzi.

        Returns:
            Surowa odpowiedź API OpenRouter.

        Raises:
            RuntimeError: Gdy brak klucza API OpenRouter.
            requests.HTTPError: Gdy API zwróci błąd HTTP.
        """

        if not self.is_enabled():
            raise RuntimeError("Brak klucza OPENROUTER_API_KEY.")

        response = requests.post(
            f"{self._settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._settings.openrouter_api_key}",
                "HTTP-Referer": self._settings.openrouter_site_url,
                "X-Title": self._settings.openrouter_app_name,
                "Content-Type": "application/json",
            },
            json={
                "model": self._settings.openrouter_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=self._settings.app_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

