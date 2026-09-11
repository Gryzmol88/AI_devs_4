"""Opcjonalny klient OpenRouter do późniejszego wsparcia analizą LLM."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from config import Settings


@dataclass(slots=True)
class OpenRouterClient:
    """Uproszczony klient OpenRouter używany opcjonalnie.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def is_enabled(self) -> bool:
        """Sprawdza, czy klient ma skonfigurowany klucz API.

        Returns:
            `True`, jeśli `OPENROUTER_API_KEY` jest ustawiony.
        """

        return bool(self.settings.openrouter_api_key)

    def simple_completion(self, prompt: str, max_tokens: int = 300) -> dict[str, Any]:
        """Wysyła proste zapytanie tekstowe do OpenRouter.

        Args:
            prompt: Treść promptu.
            max_tokens: Limit tokenów odpowiedzi.

        Returns:
            Surowa odpowiedź API jako słownik.

        Raises:
            RuntimeError: Gdy klient nie jest skonfigurowany lub żądanie kończy się błędem.
        """

        if not self.is_enabled():
            raise RuntimeError("OpenRouter nie jest skonfigurowany (brak OPENROUTER_API_KEY).")

        body = {
            "model": self.settings.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            url=f"{self.settings.openrouter_base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Błąd OpenRouter HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Błąd połączenia z OpenRouter: {error}") from error
