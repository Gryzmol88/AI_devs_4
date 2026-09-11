"""Klient HTTP do komunikacji z API `/verify/` zadania filesystem."""

from __future__ import annotations

from typing import Any

import requests

from .config import AppSettings
from .models import FsAction


class Ag3ntsVerifyClient:
    """Udostępnia metody operacji na zewnętrznym endpointzie verify."""

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta API.

        Args:
            settings: Ustawienia aplikacji zawierające URL, klucz i timeout.
        """

        self._settings = settings
        self._action_aliases = {
            "createDir": "createDirectory",
            "deleteDir": "deleteDirectory",
        }
        self._allowed_actions = {
            "createFile",
            "createDirectory",
            "deleteFile",
            "deleteDirectory",
            "reset",
            "help",
            "done",
        }

    def _normalize_action_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalizuje nazwy akcji i waliduje ich poprawność.

        Args:
            payload: Słownik akcji wysyłanej do API.

        Returns:
            dict[str, Any]: Znormalizowany payload akcji.

        Raises:
            ValueError: Gdy action jest puste lub nieobsługiwane.
        """

        action = str(payload.get("action", "")).strip()
        if not action:
            raise ValueError("Brak pola 'action' w payloadzie.")
        normalized_action = self._action_aliases.get(action, action)
        if normalized_action not in self._allowed_actions:
            raise ValueError(f"Nieobsługiwana akcja API: {normalized_action}")
        normalized_payload = dict(payload)
        normalized_payload["action"] = normalized_action
        return normalized_payload

    def send_answer(self, answer: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
        """Wysyła dowolne pole `answer` do API zadania.

        Args:
            answer: Pojedyncza akcja lub lista akcji zgodna ze specyfikacją API.

        Returns:
            dict[str, Any]: Odpowiedź API zdekodowana do słownika.

        Raises:
            RuntimeError: Gdy endpoint zwróci błąd HTTP lub niepoprawny JSON.
        """

        try:
            normalized_answer: dict[str, Any] | list[dict[str, Any]]
            if isinstance(answer, list):
                normalized_answer = [
                    self._normalize_action_payload(item) for item in answer
                ]
            else:
                normalized_answer = self._normalize_action_payload(answer)
        except ValueError as exc:
            raise RuntimeError(f"Niepoprawny payload akcji: {exc}") from exc

        payload = {
            "apikey": self._settings.ag3nts_api_key,
            "task": self._settings.task_name,
            "answer": normalized_answer,
        }
        try:
            response = requests.post(
                self._settings.ag3nts_verify_url,
                json=payload,
                timeout=self._settings.request_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = exc.response.text if exc.response is not None else ""
            raise RuntimeError(
                f"Blad HTTP verify: status={status}, body={body}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Blad polaczenia verify: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Niepoprawny JSON w odpowiedzi verify.") from exc

    def help(self) -> dict[str, Any]:
        """Pobiera opis funkcji dostępnych w API zadania.

        Returns:
            dict[str, Any]: Odpowiedź endpointu dla akcji `help`.
        """

        return self.send_answer({"action": "help"})

    def reset(self) -> dict[str, Any]:
        """Czyści zdalny filesystem poprzez akcję `reset`.

        Returns:
            dict[str, Any]: Odpowiedź endpointu dla akcji `reset`.
        """

        return self.send_answer({"action": "reset"})

    def apply_actions(self, actions: list[FsAction], use_batch: bool) -> dict[str, Any]:
        """Wysyła akcje tworzenia struktury plików.

        Args:
            actions: Lista akcji do wykonania.
            use_batch: Flaga określająca, czy wysłać wszystkie akcje jednocześnie.

        Returns:
            dict[str, Any]: Odpowiedź końcowa API.

        Efekty uboczne:
            Wysyła jedną lub wiele operacji modyfikujących zdalny filesystem.
        """

        if use_batch:
            payload = [action.to_payload() for action in actions]
            return self.send_answer(payload)

        last_response: dict[str, Any] = {}
        for action in actions:
            last_response = self.send_answer(action.to_payload())
        return last_response

    def done(self) -> dict[str, Any]:
        """Zamyka zadanie i wysyła strukturę do walidacji.

        Returns:
            dict[str, Any]: Odpowiedź endpointu dla akcji `done`.
        """

        return self.send_answer({"action": "done"})
