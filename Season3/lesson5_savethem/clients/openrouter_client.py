"""Klient OpenRouter używany do generowania pytań discovery."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import Settings


@dataclass(slots=True)
class OpenRouterClient:
    """Uproszczony klient API OpenRouter.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def generate_discovery_queries(self, context_summary: str) -> list[str]:
        """Generuje kolejne zapytania do `toolsearch` na podstawie dotychczasowych danych.

        Args:
            context_summary: Skrót zebranych informacji z poprzednich iteracji.

        Returns:
            Lista maksymalnie 5 zapytań po angielsku.
        """

        prompt = (
            "You are planning tool discovery for an AI agent solving a routing puzzle. "
            "Return ONLY JSON: {\"queries\":[\"...\"]}. "
            "Generate practical English queries for API toolsearch to obtain: map, map legend, "
            "movement rules, vehicle list, costs (food/fuel), start/goal location and constraints. "
            "Avoid duplicates and keep each query short.\n"
            f"Known context:\n{context_summary}"
        )

        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": "You produce concise JSON for tool discovery."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
            "reasoning": {"effort": self.settings.openrouter_reasoning_effort},
        }
        request = urllib.request.Request(
            url=f"{self.settings.openrouter_base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"OpenRouter connection error: {error}") from error

        content = self._extract_content(response_payload)
        parsed = self._extract_json(content)
        queries = parsed.get("queries", [])
        if not isinstance(queries, list):
            return []

        normalized: list[str] = []
        for query in queries:
            if not isinstance(query, str):
                continue
            stripped = query.strip()
            if stripped and stripped not in normalized:
                normalized.append(stripped)
        return normalized[:5]

    def _extract_content(self, payload: dict) -> str:
        """Wydobywa treść pierwszego komunikatu modelu.

        Args:
            payload: Surowa odpowiedź API.

        Returns:
            Treść wiadomości modelu lub pusty tekst.
        """

        choices = payload.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return str(message.get("content", ""))

    def _extract_json(self, text: str) -> dict:
        """Próbuje bezpiecznie odczytać JSON z treści modelu.

        Args:
            text: Tekst odpowiedzi modelu.

        Returns:
            Słownik JSON lub pusty słownik.
        """

        raw = text.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end < start:
                return {}
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return {}

