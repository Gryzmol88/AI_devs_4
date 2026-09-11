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
            "description": "Przekierowuje paczke na wskazany destination z kodem code.",
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
    payload = {"apikey": HUB_API_KEY, "action": "check", "packageid": packageid}
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(PACKAGES_API_URL, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as error:
        return {
            "ok": False,
            "error": f"Packages API HTTP {error.response.status_code}",
            "details": error.response.text[:500],
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "error": str(error)}


def redirect_package(packageid: str, destination: str, code: str) -> dict[str, Any]:
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
            return response.json()
    except httpx.HTTPStatusError as error:
        return {
            "ok": False,
            "error": f"Packages API HTTP {error.response.status_code}",
            "details": error.response.text[:500],
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "error": str(error)}
