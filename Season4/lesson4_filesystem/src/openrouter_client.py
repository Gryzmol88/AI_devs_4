"""Klient OpenRouter do ekstrakcji danych przez model językowy."""

from __future__ import annotations

import json
from typing import Any

import requests

from .config import AppSettings


class OpenRouterClient:
    """Udostępnia minimalne API do wywołania modelu OpenRouter.

    Klasa enkapsuluje format zapytania `chat/completions` i zwraca treść
    odpowiedzi modelu jako zwykły tekst.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta OpenRouter.

        Args:
            settings: Ustawienia aplikacji zawierające klucz, model i URL.
        """

        self._settings = settings

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Wysyła zapytanie do modelu i zwraca wynik JSON.

        Args:
            system_prompt: Instrukcja systemowa dla modelu.
            user_prompt: Treść wejściowa użytkownika.
            response_schema: Opcjonalny schemat odpowiedzi JSON.

        Returns:
            dict[str, Any]: Odpowiedź modelu zparsowana do słownika.

        Raises:
            RuntimeError: Gdy wywołanie API lub parsowanie JSON się nie powiedzie.
        """

        payload: dict[str, Any] = {
            "model": self._settings.openrouter_model,
            "temperature": self._settings.openrouter_temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "filesystem_extraction",
                    "strict": True,
                    "schema": response_schema,
                },
            }

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._settings.openrouter_http_referer,
            "X-Title": self._settings.openrouter_x_title,
        }

        url = f"{self._settings.openrouter_base_url.rstrip('/')}/chat/completions"
        try:
            data = self._request_json(url=url, headers=headers, payload=payload)
            content = self._extract_message_content(data)
            return json.loads(content)
        except requests.HTTPError as exc:
            if response_schema is not None and exc.response is not None and exc.response.status_code == 400:
                fallback_payload = {
                    **payload,
                    "response_format": {"type": "json_object"},
                }
                try:
                    data = self._request_json(
                        url=url,
                        headers=headers,
                        payload=fallback_payload,
                    )
                    content = self._extract_message_content(data)
                    return json.loads(content)
                except Exception as fallback_exc:  # noqa: BLE001
                    raise RuntimeError(
                        "OpenRouter odrzucił tryb json_schema i fallback json_object też się nie powiódł."
                    ) from fallback_exc
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = exc.response.text if exc.response is not None else ""
            raise RuntimeError(f"Blad HTTP OpenRouter: status={status}, body={body}") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Blad połączenia OpenRouter: {exc}") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Nie udało się zparsować JSON z odpowiedzi modelu.") from exc

    def _request_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Wysyła zapytanie HTTP i zwraca odpowiedź JSON.

        Args:
            url: Adres endpointu OpenRouter.
            headers: Nagłówki HTTP żądania.
            payload: Treść JSON wysyłana do endpointu.

        Returns:
            dict[str, Any]: Odpowiedź endpointu w postaci słownika.
        """

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self._settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _extract_message_content(self, data: dict[str, Any]) -> str:
        """Wyciąga treść wiadomości asystenta z odpowiedzi OpenRouter.

        Args:
            data: Odpowiedź endpointu `chat/completions`.

        Returns:
            str: Tekst odpowiedzi modelu.

        Raises:
            RuntimeError: Gdy pole z treścią jest puste.
        """

        content = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        )
        if not content:
            raise RuntimeError("Model zwrócił pustą odpowiedź.")
        return content
