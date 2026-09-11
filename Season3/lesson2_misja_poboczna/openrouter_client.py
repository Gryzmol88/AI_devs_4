"""Klient OpenRouter do prowadzenia pętli agentowej z Function Calling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from config import Settings
from http_utils import HttpRequestError, post_json_with_retries


class OpenRouterLimitError(RuntimeError):
    """Reprezentuje błąd limitu kredytów lub tokenów w OpenRouter."""

    def __init__(self, message: str, original_error: str) -> None:
        """Inicjalizuje wyjątek limitu OpenRouter.

        Args:
            message: Przyjazny komunikat dla użytkownika.
            original_error: Surowy komunikat błędu HTTP.
        """

        super().__init__(message)
        self.original_error = original_error


class OpenRouterContextLimitError(RuntimeError):
    """Reprezentuje błąd przekroczenia limitu kontekstu w OpenRouter."""

    def __init__(self, message: str, original_error: str) -> None:
        """Inicjalizuje wyjątek limitu kontekstu OpenRouter.

        Args:
            message: Przyjazny komunikat dla użytkownika.
            original_error: Surowy komunikat błędu HTTP.
        """

        super().__init__(message)
        self.original_error = original_error


class OpenRouterInvalidRequestError(RuntimeError):
    """Reprezentuje błąd 400 invalid request po stronie providera OpenRouter."""

    def __init__(self, message: str, original_error: str) -> None:
        """Inicjalizuje wyjątek niepoprawnego żądania OpenRouter.

        Args:
            message: Przyjazny komunikat dla użytkownika.
            original_error: Surowy komunikat błędu HTTP.
        """

        super().__init__(message)
        self.original_error = original_error


@dataclass(slots=True)
class OpenRouterClient:
    """Umożliwia wysyłanie konwersacji do modelu przez OpenRouter.

    Atrybuty:
        settings: Ustawienia aplikacji.
    """

    settings: Settings

    def _extract_openrouter_error_message(self, raw_error: str) -> str:
        """Wyciąga komunikat błędu z treści odpowiedzi OpenRouter.

        Args:
            raw_error: Surowy tekst błędu.

        Returns:
            Komunikat użytkowy wyciągnięty z odpowiedzi JSON lub tekst wejściowy.
        """

        json_start = raw_error.find("{")
        if json_start == -1:
            return raw_error

        try:
            payload = json.loads(raw_error[json_start:])
        except json.JSONDecodeError:
            return raw_error

        if isinstance(payload, dict):
            error_data = payload.get("error")
            if isinstance(error_data, dict):
                message = error_data.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        return raw_error

    def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Tworzy odpowiedź modelu z opcjonalnym użyciem narzędzi.

        Args:
            messages: Historia wiadomości w formacie chat completions.
            tools: Definicje narzędzi function calling.

        Returns:
            Odpowiedź modelu jako słownik JSON.
        """

        payload: dict[str, Any] = {
            "model": self.settings.openrouter_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "max_tokens": self.settings.openrouter_max_tokens,
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "HTTP-Referer": "https://local.lesson2.firmware",
            "X-Title": "ai-devs-season3-firmware-agent",
        }

        try:
            return post_json_with_retries(
                url=f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                payload=payload,
                headers=headers,
                timeout_seconds=self.settings.request_timeout_seconds,
                retry_limit=self.settings.retry_limit,
                backoff_base_seconds=self.settings.backoff_base_seconds,
            )
        except HttpRequestError as error:
            provider_message = self._extract_openrouter_error_message(str(error))
            if error.status_code == 400 and "invalid_request_error" in str(error).lower():
                friendly = (
                    "OpenRouter zwrócił 400 invalid request. "
                    f"Szczegóły: {provider_message}"
                )
                raise OpenRouterInvalidRequestError(
                    message=friendly,
                    original_error=str(error),
                ) from error
            if error.status_code == 400 and "maximum context length" in provider_message.lower():
                friendly = (
                    "OpenRouter zwrócił limit kontekstu 400. "
                    f"Szczegóły: {provider_message}"
                )
                raise OpenRouterContextLimitError(
                    message=friendly,
                    original_error=str(error),
                ) from error
            if error.status_code == 402:
                friendly = (
                    "OpenRouter zwrócił limit 402 (kredyty/tokeny). "
                    f"Szczegóły: {provider_message}"
                )
                raise OpenRouterLimitError(
                    message=friendly,
                    original_error=str(error),
                ) from error
            raise
