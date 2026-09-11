"""Klient HTTP do komunikacji z API zadania domatowo."""

from __future__ import annotations

from typing import Any

import requests

from .config import AppSettings


class Ag3ntsApiClient:
    """Udostępnia metody wysyłania akcji do endpointu `/verify`.

    Klasa enkapsuluje format żądania wymagany przez zadanie:
    `apikey`, `task`, `answer`.
    """

    def __init__(self, settings: AppSettings, task_name: str | None = None) -> None:
        """Inicjalizuje klienta API.

        Args:
            settings: Ustawienia aplikacji zawierające URL, klucz i timeout.
            task_name: Nazwa zadania wysyłana w polu `task`.
                Gdy nie podano, używana jest wartość z konfiguracji.
        """

        self._settings = settings
        self._task_name = task_name or settings.task_name

    def send_action(self, answer: dict[str, Any]) -> dict[str, Any]:
        """Wysyła pojedynczą akcję do API i zwraca odpowiedź JSON.

        Args:
            answer: Pole `answer` zgodne ze specyfikacją zadania.

        Returns:
            dict[str, Any]: Odpowiedź API zdekodowana do słownika.

        Raises:
            RuntimeError: Gdy endpoint zwróci błąd HTTP lub niepoprawny JSON.
        """

        payload = {
            "apikey": self._settings.ag3nts_api_key,
            "task": self._task_name,
            "answer": answer,
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
                f"Blad HTTP podczas akcji {answer}: status={status}, body={body}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Blad HTTP podczas akcji {answer}: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError(f"Niepoprawny JSON w odpowiedzi dla akcji {answer}") from exc
