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
            message: Opis błędu.
            status_code: Kod HTTP, jeśli jest dostępny.
        """

        super().__init__(message)
        self.status_code = status_code


def compute_backoff_seconds(
    attempt: int,
    base_seconds: float,
    jitter_min: float = 0.0,
    jitter_max: float = 0.35,
) -> float:
    """Oblicza opóźnienie backoff dla kolejnej próby.

    Args:
        attempt: Numer próby (od 1).
        base_seconds: Bazowy czas opóźnienia.
        jitter_min: Minimalny jitter losowy.
        jitter_max: Maksymalny jitter losowy.

    Returns:
        Czas oczekiwania w sekundach.
    """

    exponential = base_seconds * (2 ** max(0, attempt - 1))
    jitter = random.uniform(jitter_min, jitter_max)
    return exponential + jitter


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Wysyła żądanie POST JSON i zwraca odpowiedź jako słownik.

    Args:
        url: Adres endpointu.
        payload: Dane wysyłane w body.
        headers: Dodatkowe nagłówki HTTP.
        timeout_seconds: Timeout żądania.

    Returns:
        Odpowiedź API zdekodowana do słownika.

    Raises:
        HttpRequestError: Gdy wystąpi błąd HTTP, połączenia lub JSON.
    """

    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
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
    retry_statuses: set[int] | None = None,
) -> dict[str, Any]:
    """Wysyła POST JSON z ponowieniami dla błędów przejściowych.

    Args:
        url: Adres endpointu.
        payload: Dane żądania.
        timeout_seconds: Timeout pojedynczego wywołania.
        retry_limit: Maksymalna liczba prób.
        backoff_base_seconds: Bazowy backoff.
        headers: Dodatkowe nagłówki.
        retry_statuses: Kody HTTP kwalifikujące do ponowienia.

    Returns:
        Odpowiedź API jako słownik.

    Raises:
        HttpRequestError: Gdy wszystkie próby zakończą się błędem.
    """

    retriable = retry_statuses or {408, 425, 429, 500, 502, 503, 504}
    last_error: HttpRequestError | None = None

    for attempt in range(1, retry_limit + 1):
        try:
            return post_json(
                url=url,
                payload=payload,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except HttpRequestError as error:
            last_error = error
            should_retry = error.status_code is None or error.status_code in retriable
            if not should_retry or attempt >= retry_limit:
                break
            time.sleep(
                compute_backoff_seconds(
                    attempt=attempt,
                    base_seconds=backoff_base_seconds,
                )
            )

    assert last_error is not None
    raise last_error
