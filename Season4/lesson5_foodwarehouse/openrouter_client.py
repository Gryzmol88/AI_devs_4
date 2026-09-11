"""Integracja z OpenRouter do pomocniczych analiz agentowych."""

import json
from typing import Any
from urllib import request

from config import Settings


class OpenRouterClient:
    """Klient API OpenRouter dla pojedynczych zapytań chatowych.

    Args:
        settings: Konfiguracja aplikacji z kluczem i modelem.
    """

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klienta OpenRouter.

        Args:
            settings: Konfiguracja aplikacji.
        """

        self._settings = settings

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Wysyła zapytanie do modelu i zwraca tekst odpowiedzi.

        Args:
            system_prompt: Instrukcja systemowa agenta.
            user_prompt: Treść zapytania użytkownika.

        Returns:
            Tekst odpowiedzi modelu.
        """

        url = f"{self._settings.openrouter_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=url,
            data=data,
            headers={
                "Authorization": f"Bearer {self._settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with request.urlopen(req, timeout=self._settings.request_timeout_seconds) as response:
            content = response.read().decode("utf-8")
            raw: dict[str, Any] = json.loads(content)
            return str(raw["choices"][0]["message"]["content"])

