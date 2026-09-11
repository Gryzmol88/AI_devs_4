"""Klient HTTP do wywołań OpenRouter vision używanych w analizie mapy."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import AppSettings, RuntimeConfig
from .schemas import CoordinateResult


class OpenRouterVisionClient:
    """Lekki wrapper OpenRouter wyspecjalizowany w pojedynczym żądaniu vision."""

    def __init__(self, settings: AppSettings, runtime_cfg: RuntimeConfig) -> None:
        """Przechowuje ustawienia wymagane do autoryzowanych wywołań API."""

        self._settings = settings
        self._runtime_cfg = runtime_cfg

    def build_payload(self) -> dict[str, Any]:
        """Buduje deterministyczny payload czatu wymagający ścisłego JSON-a."""

        prompt_text = (
            "Przeanalizuj mapę z siatką sektorów i wskaż sektor tamy. "
            "Sektory są podzielone czerwonymi liniami siatki - licz kolumny i wiersze na podstawie tych czerwonych linii. "
            "Współrzędne podaj jako kolumna (x) i wiersz (y), indeksowanie od 1. "
            "Zwróć WYŁĄCZNIE obiekt JSON z polami: "
            "col, row, grid_cols, grid_rows, confidence, reasoning_short."
        )

        return {
            "model": self._runtime_cfg.vision_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Jesteś precyzyjnym analitykiem vision. "
                        "Wykrywaj siatkę wyłącznie po czerwonych liniach podziału sektorów. "
                        "Zwracasz tylko poprawny JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": self._runtime_cfg.map_url}},
                    ],
                },
            ],
        }

    def call(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Wysyła żądanie do OpenRouter `/chat/completions` i zwraca JSON + status."""

        url = f"{self._runtime_cfg.openrouter_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self._runtime_cfg.request_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)

        response.raise_for_status()
        return response.json(), response.status_code

    def extract_text(self, response_json: dict[str, Any]) -> str:
        """Wyciąga tekst odpowiedzi asystenta z formatu odpowiedzi OpenRouter."""

        choices = response_json.get("choices", [])
        if not choices:
            raise ValueError("Odpowiedź OpenRouter nie zawiera pola `choices`.")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            # Część providerów zwraca listę chunków zawierających węzły tekstowe.
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")).strip())
            return "\n".join(part for part in text_parts if part).strip()

        return str(content).strip()

    def parse_coordinate_result(self, text: str) -> CoordinateResult:
        """Parsuje JSON z tekstu modelu i waliduje go schematem Pydantic."""

        parsed = self._extract_json_object(text)
        return CoordinateResult.model_validate(parsed)

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        """Wyodrębnia pierwszy obiekt JSON z tekstu i bezpiecznie go dekoduje."""

        # To wyrażenie regularne celowo znajduje szeroki kandydat obiektu,
        # aby obsłużyć przypadki, gdy model otacza JSON markdownem lub dopiskami.
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("Odpowiedź modelu nie zawiera obiektu JSON.")
        return json.loads(match.group(0))
