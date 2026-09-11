"""Klient OpenRouter wspierający normalizację zapytań w języku naturalnym."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import Settings


@dataclass(slots=True)
class OpenRouterClient:
    """Uproszczony klient OpenRouter wykorzystywany jako fallback parsera.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def is_enabled(self) -> bool:
        """Sprawdza, czy klient jest gotowy do wywołań API.

        Returns:
            `True`, gdy ustawiono klucz API i aktywowano parser LLM.
        """

        return bool(self.settings.openrouter_api_key) and self.settings.enable_llm_parser

    def extract_items(self, query: str, known_items: list[str]) -> list[str]:
        """Prosi model o wskazanie przedmiotów obecnych w zapytaniu.

        Args:
            query: Treść zapytania agenta.
            known_items: Lista znanych nazw przedmiotów, z których model ma wybierać.

        Returns:
            Lista przedmiotów wskazanych przez model i obecnych w `known_items`.

        Raises:
            RuntimeError: Gdy API zwróci błąd HTTP lub odpowiedź ma zły format.
        """

        if not self.is_enabled():
            return []

        item_preview = ", ".join(known_items[:250])
        prompt = (
            "Zwróć wyłącznie JSON bez komentarza w formacie "
            '{"items":["..."]}. '
            "Wybieraj tylko pozycje z listy known_items. "
            "Jeśli brak dopasowania, zwróć pustą listę. "
            f"known_items: [{item_preview}] "
            f"query: {query}"
        )
        body = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": "Jesteś parserem danych wejściowych dla narzędzi."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 200,
        }
        request = urllib.request.Request(
            url=f"{self.settings.openrouter_base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {error.code}: {details}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Błąd połączenia OpenRouter: {error}") from error

        content = self._extract_content(payload)
        parsed = self._extract_json(content)
        items = parsed.get("items", [])
        if not isinstance(items, list):
            return []
        known_lookup = {item.lower(): item for item in known_items}
        resolved: list[str] = []
        for item in items:
            if not isinstance(item, str):
                continue
            normalized = item.lower().strip()
            if normalized in known_lookup:
                resolved.append(known_lookup[normalized])
        return resolved

    def _extract_content(self, payload: dict) -> str:
        """Wyciąga treść odpowiedzi modelu z payloadu API.

        Args:
            payload: Surowy payload zwrócony przez OpenRouter.

        Returns:
            Treść wiadomości modelu.
        """

        choices = payload.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        content = message.get("content", "")
        return str(content)

    def _extract_json(self, content: str) -> dict:
        """Próbuje sparsować JSON z odpowiedzi modelu.

        Args:
            content: Tekst odpowiedzi modelu.

        Returns:
            Słownik JSON lub pusty słownik przy błędzie parsowania.
        """

        content = content.strip()
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                return {}

