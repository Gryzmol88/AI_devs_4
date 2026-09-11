from typing import Any

import httpx

from .config import HUB_API_KEY, PACKAGES_API_URL

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_package",
            "description": "Sprawdza status paczki po packageid.",
            "parameters": {
                "type": "object",
                "properties": {"packageid": {"type": "string"}},
                "required": ["packageid"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redirect_package",
            "description": "Przekierowuje paczkę na wskazaną destynację z kodem autoryzacji.",
            "parameters": {
                "type": "object",
                "properties": {
                    "packageid": {"type": "string"},
                    "destination": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["packageid", "destination", "code"],
                "additionalProperties": False,
            },
        },
    },
]


def check_package(packageid: str) -> dict[str, Any]:
    # Narzedzie mapuje 1:1 na API "check".
    payload = {"apikey": HUB_API_KEY, "action": "check", "packageid": packageid}
    print(f"[tool] check_package packageid={packageid}")
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(PACKAGES_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            print(f"[tool] check_package ok status={response.status_code}")
            return data
    except httpx.HTTPStatusError as error:
        print(f"[tool] check_package http_error status={error.response.status_code}")
        return {
            "ok": False,
            "error": f"Packages API HTTP {error.response.status_code}",
            "details": error.response.text[:500],
        }
    except Exception as error:  # noqa: BLE001
        print(f"[tool] check_package error={error}")
        return {"ok": False, "error": str(error)}


def redirect_package(packageid: str, destination: str, code: str) -> dict[str, Any]:
    # Narzedzie mapuje 1:1 na API "redirect".
    print(
        f"[tool] redirect_package packageid={packageid} "
        f"destination={destination} code_len={len(code)}"
    )
    payload = {
        "apikey": HUB_API_KEY,
        "action": "redirect",
        "packageid": packageid,
        "destination": destination,
        "code": code,
    }
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(PACKAGES_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            print(f"[tool] redirect_package ok status={response.status_code}")
            return data
    except httpx.HTTPStatusError as error:
        print(f"[tool] redirect_package http_error status={error.response.status_code}")
        return {
            "ok": False,
            "error": f"Packages API HTTP {error.response.status_code}",
            "details": error.response.text[:500],
        }
    except Exception as error:  # noqa: BLE001
        print(f"[tool] redirect_package error={error}")
        return {"ok": False, "error": str(error)}
