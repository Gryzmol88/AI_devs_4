"""Kolektor raportow asynchronicznych z API windpower."""

from __future__ import annotations

import time
from typing import Any

from clients.aidevs_api import AIDevsApiClient
from config import AppSettings
from utils.logger import log_info, log_warn


class ReportCollector:
    """Pobiera raporty kolejkowane przez API zadania.

    Klasa zaklada, ze najpierw trzeba zlecic akcje raportowe, a potem odpytywac
    `getResult` do czasu uzyskania gotowego wyniku.
    """

    def __init__(self, settings: AppSettings, api_client: AIDevsApiClient) -> None:
        """Tworzy kolektor raportow.

        Args:
            settings: Konfiguracja aplikacji.
            api_client: Klient API do komunikacji z endpointem verify.
        """

        self._settings = settings
        self._api_client = api_client
        self._last_trace: list[dict[str, Any]] = []

    def enqueue_params(self, params: list[str]) -> dict[str, dict[str, Any]]:
        """Zleca podane parametry raportowe do kolejki API.

        Args:
            params: Lista nazw parametrow akcji `get`.

        Returns:
            Slownik mapujacy parametr na odpowiedz API po zleceniu.
        """

        enqueued: dict[str, dict[str, Any]] = {}
        for param in params:
            response = self._api_client.get(param=param)
            enqueued[param] = response
            log_info(f"Zlecono raport get/{param}")
        return enqueued

    def collect_results(self, expected_sources: set[str]) -> dict[str, dict[str, Any]]:
        """Pobiera wyniki raportow az do uzyskania kompletu lub timeoutu.

        Args:
            expected_sources: Zbior oczekiwanych pol `sourceFunction`.

        Returns:
            Slownik mapujacy sourceFunction na finalny wynik raportu.
        """

        results: dict[str, dict[str, Any]] = {}
        self._last_trace = []
        deadline = time.monotonic() + self._settings.app_poll_timeout_seconds
        pending = set(expected_sources)

        while pending and time.monotonic() < deadline:
            try:
                response = self._api_client.get_result()
            except Exception:  # noqa: BLE001
                time.sleep(self._settings.app_poll_interval_seconds)
                continue
            self._last_trace.append(response)
            source = self._extract_source_function(response=response)
            if source and source in pending and self._is_result_ready(response=response):
                results[source] = response
                pending.remove(source)
                log_info(f"Odebrano raport: {source}")
            else:
                time.sleep(self._settings.app_poll_interval_seconds)

        if pending:
            missing = ", ".join(sorted(pending))
            log_warn(f"Nie odebrano wszystkich raportow przed timeoutem: {missing}")

        return results

    def get_last_trace(self) -> list[dict[str, Any]]:
        """Zwraca surowy trace odpowiedzi getResult z ostatniego pollingu.

        Returns:
            Lista odpowiedzi API odebranych podczas ostatniego collect_results.
        """

        return list(self._last_trace)

    @staticmethod
    def _extract_source_function(response: dict[str, Any]) -> str:
        """Wydobywa sourceFunction z odpowiedzi getResult.

        Args:
            response: Odpowiedz API dla getResult.

        Returns:
            Nazwa funkcji zrodlowej lub pusty string.
        """

        source = response.get("sourceFunction")
        if isinstance(source, str) and source:
            return source
        for key in ("result", "data", "message"):
            nested = response.get(key)
            if isinstance(nested, dict):
                nested_source = nested.get("sourceFunction")
                if isinstance(nested_source, str) and nested_source:
                    return nested_source
        return ""

    @staticmethod
    def _is_result_ready(response: dict[str, Any]) -> bool:
        """Ocena, czy wynik getResult jest gotowy.

        Args:
            response: Odpowiedz API z akcji getResult.

        Returns:
            True, jesli odpowiedz zawiera gotowe dane.
        """

        source = ReportCollector._extract_source_function(response=response)
        if source:
            message_text = str(response.get("message", "")).lower()
            if "queue" in message_text and ("empty" in message_text or "pending" in message_text):
                return False
            return True
        if response.get("status") in {"done", "ready", "ok", "success"}:
            return True
        for key in ("result", "data", "report", "payload"):
            value = response.get(key)
            if isinstance(value, dict) and value:
                return True
            if isinstance(value, list) and value:
                return True
        if response.get("code") == 0:
            return True
        return False
