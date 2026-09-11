"""Klient API verify z metadanymi czasowymi wywolan."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from config import AppSettings


class AIDevsApiClient:
    """Klient API dla misji windpower/pobocznej."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._session = requests.Session()

    @staticmethod
    def _iso_now() -> str:
        return datetime.now().isoformat(timespec="milliseconds")

    def call(self, answer: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Wysyla request i zwraca (response_json, trace)."""

        request_payload = {
            "apikey": self._settings.aidevs_api_key,
            "task": self._settings.aidevs_task,
            "answer": answer,
        }
        started_at = self._iso_now()
        response = self._session.post(
            self._settings.aidevs_verify_url,
            json=request_payload,
            timeout=self._settings.app_timeout_seconds,
        )
        finished_at = self._iso_now()

        response_payload: dict[str, Any]
        try:
            response_payload = response.json()
        except Exception:  # noqa: BLE001
            response_payload = {"rawText": response.text}

        trace = {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "request": {
                "task": self._settings.aidevs_task,
                "answer": answer,
            },
            "http": {
                "statusCode": response.status_code,
                "ok": response.ok,
            },
            "response": response_payload,
        }

        if not response.ok:
            details = response.text.strip()
            raise requests.HTTPError(
                f"{response.status_code} HTTP error for {response.url}. API details: {details}",
                response=response,
            )
        return response_payload, trace
