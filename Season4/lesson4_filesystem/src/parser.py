"""Parser notatek Natana oparty o ekstrakcję LLM przez OpenRouter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ExtractedKnowledge
from .openrouter_client import OpenRouterClient


def _extraction_schema() -> dict[str, Any]:
    """Buduje schemat JSON dla odpowiedzi modelu ekstrakcyjnego.

    Returns:
        dict[str, Any]: Schemat JSON Schema dla danych zadania filesystem.
    """

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "cities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "needs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "item": {"type": "string"},
                                    "amount": {"type": "integer"},
                                },
                                "required": ["item", "amount"],
                            },
                        },
                    },
                    "required": ["name", "needs"],
                },
            },
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "full_name": {"type": "string"},
                        "city": {"type": "string"},
                    },
                    "required": ["full_name", "city"],
                },
            },
            "offers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "item": {"type": "string"},
                        "city": {"type": "string"},
                    },
                    "required": ["item", "city"],
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["cities", "people", "offers", "notes"],
    }


class NotesParser:
    """Realizuje ekstrakcję miast, osób i towarów z surowych notatek."""

    def __init__(self, client: OpenRouterClient, prompt_path: Path) -> None:
        """Inicjalizuje parser notatek.

        Args:
            client: Klient OpenRouter wykorzystywany do ekstrakcji.
            prompt_path: Ścieżka do pliku z instrukcją systemową.
        """

        self._client = client
        self._prompt_path = prompt_path

    def _load_system_prompt(self) -> str:
        """Wczytuje treść promptu systemowego z pliku.

        Returns:
            str: Prompt systemowy używany do ekstrakcji.
        """

        return self._prompt_path.read_text(encoding="utf-8")

    def extract_knowledge(self, raw_notes: str) -> ExtractedKnowledge:
        """Ekstrahuje dane domenowe z surowych notatek.

        Args:
            raw_notes: Treść notatek Natana po scaleniu źródeł.

        Returns:
            ExtractedKnowledge: Dane gotowe do etapu normalizacji.
        """

        system_prompt = self._load_system_prompt()
        user_prompt = (
            "Przeanalizuj notatki i zwróć wyłącznie JSON zgodny ze schematem.\n\n"
            f"NOTATKI:\n{raw_notes}"
        )
        response_json = self._client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=_extraction_schema(),
        )
        return ExtractedKnowledge.model_validate(response_json)

