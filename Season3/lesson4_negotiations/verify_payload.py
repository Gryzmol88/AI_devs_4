"""Budowanie payloadów do zgłoszenia i sprawdzenia zadania negotiations."""

from __future__ import annotations

import json

from config import get_settings


def build_tools_payload(public_base_url: str) -> dict:
    """Tworzy payload zgłoszeniowy `tools` dla endpointu `/verify`.

    Args:
        public_base_url: Publiczny adres bazowy API (np. domena ngrok).

    Returns:
        Słownik gotowy do wysłania metodą POST na `VERIFY_URL`.
    """

    settings = get_settings()
    base = public_base_url.rstrip("/")
    return {
        "apikey": settings.hub_api_key,
        "task": settings.task_name,
        "answer": {
            "tools": [
                {
                    "URL": f"{base}/api/find-cities",
                    "description": (
                        "Narzędzie do wyszukiwania miast, które sprzedają wymagane przedmioty. "
                        "Przekazuj w polu params naturalny opis jednego lub wielu przedmiotów, "
                        "np. 'szukam kabla 10m i sterownika'. Odpowiedź zwraca miasta mające komplet."
                    ),
                }
            ]
        },
    }


def build_check_payload() -> dict:
    """Tworzy payload do asynchronicznego sprawdzenia wyniku zadania.

    Returns:
        Słownik do wysłania na `/verify` z akcją `check`.
    """

    settings = get_settings()
    return {
        "apikey": settings.hub_api_key,
        "task": settings.task_name,
        "answer": {"action": "check"},
    }


if __name__ == "__main__":
    settings = get_settings()
    example_base_url = "https://twoj-ngrok.ngrok-free.app"
    print("# VERIFY_URL:", settings.verify_url)
    print("# Payload tools:")
    print(json.dumps(build_tools_payload(example_base_url), ensure_ascii=False, indent=2))
    print("\n# Payload check:")
    print(json.dumps(build_check_payload(), ensure_ascii=False, indent=2))

