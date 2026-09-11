"""Klient OpenRouter do opcjonalnego zgadywania nazwy taska pobocznego."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import Settings


@dataclass(slots=True)
class OpenRouterClient:
    """Uproszczony klient OpenRouter.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def enabled(self) -> bool:
        """Sprawdza, czy klient OpenRouter jest aktywny.

        Returns:
            `True`, jeśli ustawiono klucz API i aktywację guessera.
        """

        return bool(self.settings.openrouter_api_key.strip()) and self.settings.use_openrouter_task_guesser

    def guess_task_names(self, hint: str, known_candidates: list[str]) -> list[str]:
        """Generuje dodatkowe kandydaty nazw taska.

        Args:
            hint: Podpowiedź misji.
            known_candidates: Znane kandydaty taska.

        Returns:
            Lista nowych kandydatów (wyłącznie litery).
        """

        if not self.enabled():
            return []

        prompt = (
            "Return ONLY JSON: {\"tasks\":[\"...\"]}. "
            "Generate lowercase task names made of letters only. "
            "Context: side mission related to savethem, hint in Polish: "
            f"'{hint}'. Existing candidates: {known_candidates}."
        )
        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": "You return only concise JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 200,
            "reasoning": {"effort": self.settings.openrouter_reasoning_effort},
        }
        request = urllib.request.Request(
            url=f"{self.settings.openrouter_base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
            return []

        content = ""
        choices = raw.get("choices", [])
        if choices:
            content = str(choices[0].get("message", {}).get("content", "")).strip()

        parsed = _safe_json(content)
        tasks = parsed.get("tasks", [])
        if not isinstance(tasks, list):
            return []
        result: list[str] = []
        for item in tasks:
            if not isinstance(item, str):
                continue
            candidate = item.strip().lower()
            if candidate.isalpha() and candidate not in result:
                result.append(candidate)
        return result


def _safe_json(text: str) -> dict:
    """Parsuje JSON z tekstu modelu.

    Args:
        text: Tekst odpowiedzi modelu.

    Returns:
        Zdeserializowany słownik lub pusty słownik.
    """

    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return {}
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}

