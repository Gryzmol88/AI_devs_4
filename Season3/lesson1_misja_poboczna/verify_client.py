"""Klient HTTP do wysyłki kandydatów misji pobocznej."""

from __future__ import annotations

import json
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def submit_candidate(
    verify_url: str,
    api_key: str,
    task_name: str,
    candidate: Any,
    timeout_seconds: int = 30,
) -> Dict[str, object]:
    """Wysyła pojedynczego kandydata odpowiedzi do endpointu verify.

    Args:
        verify_url: Adres endpointu `/verify`.
        api_key: Klucz API.
        task_name: Nazwa zadania.
        candidate: Kandydat odpowiedzi (obiekt JSON lub tablica JSON).
        timeout_seconds: Timeout żądania HTTP.

    Returns:
        Słownik z odpowiedzią API lub błędem.
    """

    payload = {"apikey": api_key, "task": task_name, "answer": candidate}
    request = Request(
        verify_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec: B310
            raw = response.read().decode("utf-8")
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
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"ok": True, "raw_response": raw}
