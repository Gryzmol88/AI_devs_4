"""Agent analityczny wykorzystujący OpenRouter do priorytetyzacji pól mapy."""

from __future__ import annotations

import re
from typing import Any

import requests

from ..config import AppSettings


class IntelAgent:
    """Realizuje lekką analizę sygnału i mapy przez model LLM.

    Agent nie podejmuje decyzji wykonawczych w API. Zwraca jedynie sugestie,
    które są następnie filtrowane przez planistę deterministycznego.
    """

    _CELL_PATTERN = re.compile(r"\b([A-K](?:10|11|[1-9]))\b", re.IGNORECASE)

    def __init__(self, settings: AppSettings) -> None:
        """Tworzy agenta analitycznego.

        Args:
            settings: Ustawienia zawierające parametry integracji z OpenRouter.
        """

        self._settings = settings

    def suggest_cells(
        self,
        map_payload: dict[str, Any],
        radio_message: str,
    ) -> dict[str, Any]:
        """Zwraca pola mapy zasugerowane przez LLM jako priorytetowe.

        Args:
            map_payload: Surowa odpowiedź mapy użyta jako kontekst.
            radio_message: Treść przechwyconego komunikatu radiowego.

        Returns:
            dict[str, Any]: Słownik z listą pól pod kluczem `cells` i notatką `reason`.
        """

        if not self._settings.openrouter_api_key:
            return {
                "cells": [],
                "reason": "Brak OPENROUTER_API_KEY, pomijam analize LLM.",
            }

        prompt = (
            "Masz wskazac maksymalnie 20 pol mapy 11x11 (A1-K11), ktore warto "
            "sprawdzic najpierw. Odpowiedz w JSON: "
            '{"cells":["F6","G6"],"reason":"..."}.\n'
            f"Radio: {radio_message}\n"
            f"Mapa: {map_payload}"
        )
        payload = {
            "model": self._settings.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._settings.openrouter_http_referer,
            "X-Title": self._settings.openrouter_x_title,
        }
        try:
            response = requests.post(
                f"{self._settings.openrouter_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self._settings.request_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            candidates = [c.upper() for c in self._CELL_PATTERN.findall(text)]
            unique_cells = list(dict.fromkeys(candidates))
            return {"cells": unique_cells, "reason": "Sugestie z OpenRouter."}
        except Exception as exc:  # noqa: BLE001
            return {
                "cells": [],
                "reason": f"Analiza LLM nieudana, fallback do planu deterministycznego: {exc}",
            }

