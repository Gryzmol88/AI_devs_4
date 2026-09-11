"""Silnik eksploracji payloadów misji pobocznej przez endpoint `/verify`."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from config import Settings
from http_utils import HttpRequestError, JsonHttpClient
from models import AttemptResult, find_flag_in_payload


@dataclass(slots=True)
class VerifyExplorer:
    """Wysyła warianty payloadów i zbiera odpowiedzi pod kątem flag.

    Atrybuty:
        settings: Konfiguracja aplikacji.
        client: Klient HTTP JSON.
    """

    settings: Settings
    client: JsonHttpClient

    def run(self, candidates: list[tuple[str, dict[str, Any]]]) -> list[AttemptResult]:
        """Uruchamia kolejne próby payloadów do limitu konfiguracji.

        Args:
            candidates: Lista krotek `(etykieta, payload)`.

        Returns:
            Lista rezultatów prób wraz z odpowiedziami i wykrytą flagą.
        """

        results: list[AttemptResult] = []
        for idx, (label, payload) in enumerate(candidates[: self.settings.max_payload_attempts], start=1):
            try:
                response = self.client.post_json(self.settings.verify_url, payload)
                found_flag = find_flag_in_payload(response)
                notes: list[str] = []
                poll_results: list[dict[str, Any]] = []
                if self._is_tools_submission(payload) and self._is_queued(response):
                    poll_results = self._poll_check()
                    for poll in poll_results:
                        poll_flag = find_flag_in_payload(poll)
                        if poll_flag:
                            found_flag = poll_flag
                            notes.append("flag_found_in_poll")
                            break
                    if poll_results:
                        response = {**response, "check_polls": poll_results}
            except HttpRequestError as error:
                response = {"error": str(error), "status_code": error.status_code}
                found_flag = None
                notes = ["http_error"]

            results.append(
                AttemptResult(
                    attempt_index=idx,
                    label=label,
                    payload=payload,
                    response=response,
                    found_flag=found_flag,
                    notes=notes,
                )
            )
            if found_flag and not self._is_main_flag(found_flag):
                break
        return results

    def _is_main_flag(self, flag: str) -> bool:
        """Sprawdza, czy wykryta flaga wygląda na znaną flagę główną.

        Args:
            flag: Wykryta flaga.

        Returns:
            `True`, jeśli to flaga główna `WINDFARM`.
        """

        return flag.strip().upper() == "{FLG:WINDFARM}"

    def _is_tools_submission(self, payload: dict[str, Any]) -> bool:
        """Sprawdza, czy payload wygląda na zgłoszenie narzędzi.

        Args:
            payload: Wysłany payload.

        Returns:
            `True`, jeśli w `answer` obecne jest pole `tools`.
        """

        answer = payload.get("answer")
        return isinstance(answer, dict) and isinstance(answer.get("tools"), list)

    def _is_queued(self, response: dict[str, Any]) -> bool:
        """Sprawdza, czy odpowiedź sygnalizuje kolejkę asynchroniczną.

        Args:
            response: Odpowiedź `/verify`.

        Returns:
            `True`, gdy API zwraca kod 0 i komunikat o kolejce.
        """

        code = response.get("code")
        message = str(response.get("message", "")).lower()
        return code == 0 and "queued" in message

    def _poll_check(self) -> list[dict[str, Any]]:
        """Wysyła serię zapytań `action=check` po zgłoszeniu narzędzi.

        Returns:
            Lista odpowiedzi z kolejnych prób `check`.
        """

        results: list[dict[str, Any]] = []
        check_payload = {
            "apikey": self.settings.hub_api_key,
            "task": self.settings.task_name,
            "answer": {"action": "check"},
        }
        for _ in range(self.settings.check_poll_retries):
            time.sleep(max(0.0, self.settings.check_poll_delay_seconds))
            try:
                response = self.client.post_json(self.settings.verify_url, check_payload)
            except HttpRequestError as error:
                response = {"error": str(error), "status_code": error.status_code}
            results.append(response)
            if find_flag_in_payload(response):
                break
            if response.get("code") not in {-500, 0}:
                # Zatrzymujemy polling, gdy serwer zwróci konkretny wynik końcowy.
                break
        return results
