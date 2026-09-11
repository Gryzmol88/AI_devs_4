"""Pomocnicze funkcje HTTP z retry i obsługą błędów."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any


class HttpRequestError(RuntimeError):
    """Reprezentuje błąd komunikacji HTTP."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Inicjalizuje wyjątek błędu HTTP.

        Args:
            message: Treść błędu.
            status_code: Kod HTTP, jeśli jest dostępny.
        """

        super().__init__(message)
        self.status_code = status_code


def compute_backoff_seconds(attempt: int, base_seconds: float) -> float:
    """Oblicza opóźnienie backoff dla kolejnej próby.

    Args:
        attempt: Numer próby od 1.
        base_seconds: Bazowa liczba sekund.

    Returns:
        Opóźnienie w sekundach z jitterem.
    """

    jitter = random.uniform(0.0, 0.35)
    return base_seconds * (2 ** max(0, attempt - 1)) + jitter


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Wysyła żądanie POST JSON i zwraca odpowiedź jako słownik.

    Args:
        url: Adres endpointu.
        payload: Dane JSON wysyłane w body.
        timeout_seconds: Timeout żądania.
        headers: Opcjonalne nagłówki HTTP.

    Returns:
        Odpowiedź API zdekodowana jako słownik.

    Raises:
        HttpRequestError: Gdy wystąpi błąd połączenia, HTTP lub JSON.
    """

    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise HttpRequestError(
            message=f"HTTP {error.code} dla {url}: {body}",
            status_code=error.code,
        ) from error
    except urllib.error.URLError as error:
        raise HttpRequestError(message=f"Błąd połączenia dla {url}: {error}") from error
    except json.JSONDecodeError as error:
        raise HttpRequestError(message=f"Niepoprawny JSON z {url}: {error}") from error


def post_json_with_retries(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    retry_limit: int,
    backoff_base_seconds: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Wysyła POST JSON z automatycznymi ponowieniami.

    Args:
        url: Adres endpointu.
        payload: Dane JSON żądania.
        timeout_seconds: Timeout pojedynczego żądania.
        retry_limit: Maksymalna liczba prób.
        backoff_base_seconds: Bazowe opóźnienie backoff.
        headers: Opcjonalne nagłówki HTTP.

    Returns:
        Odpowiedź API jako słownik.

    Raises:
        HttpRequestError: Gdy wszystkie próby zakończą się błędem.
    """

    retriable_statuses = {408, 425, 429, 500, 502, 503, 504}
    last_error: HttpRequestError | None = None

    for attempt in range(1, retry_limit + 1):
        try:
            return post_json(
                url=url,
                payload=payload,
                timeout_seconds=timeout_seconds,
                headers=headers,
            )
        except HttpRequestError as error:
            last_error = error
            should_retry = error.status_code is None or error.status_code in retriable_statuses
            if not should_retry or attempt >= retry_limit:
                break
            time.sleep(compute_backoff_seconds(attempt=attempt, base_seconds=backoff_base_seconds))

    assert last_error is not None
    raise last_error
