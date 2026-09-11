"""Klient HTTP do wysyłki końcowej odpowiedzi na endpoint weryfikacyjny."""

from __future__ import annotations

import json
from typing import Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from models import FinalResult


def submit_verification(payload: FinalResult, verify_url: str, timeout_seconds: int = 30) -> Dict[str, object]:
    """Wysyła finalny payload do endpointu weryfikacyjnego.

    Args:
        payload: Finalny payload zadania.
        verify_url: URL endpointu weryfikacji.
        timeout_seconds: Limit czasu HTTP w sekundach.

    Returns:
        Sparsowaną odpowiedź JSON lub słownik awaryjny przy błędzie parsowania.
    """

    request = Request(
        verify_url,
        data=payload.model_dump_json().encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec: B310
            raw_text = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = ""
        return {
            "ok": False,
            "error": f"HTTPError {exc.code}",
            "details": str(exc),
            "response_body": error_body,
        }
    except URLError as exc:
        return {"ok": False, "error": "URLError", "details": str(exc)}

    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"ok": True, "raw_response": raw_text}
