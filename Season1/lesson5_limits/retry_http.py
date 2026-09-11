"""Small HTTP client with retry and rate-limit guard."""

from __future__ import annotations

import random
import time
from typing import Any

import requests

try:
    from .rate_limit import get_rate_limit_sleep_seconds
except ImportError:
    from rate_limit import get_rate_limit_sleep_seconds


def _is_retryable_status(status_code: int) -> bool:
    """Return True when HTTP status should be retried."""

    return status_code == 429 or status_code == 503 or 500 <= status_code <= 599


def _retry_delay(attempt: int, base_delay_seconds: float, max_jitter_seconds: float) -> float:
    """Calculate exponential backoff delay with jitter."""

    exponential = base_delay_seconds * (2 ** (attempt - 1))
    jitter = random.uniform(0.0, max_jitter_seconds)
    return exponential + jitter


def post_json_with_retry(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    max_retries: int,
    base_delay_seconds: float,
    max_jitter_seconds: float,
    session: requests.Session | None = None,
) -> requests.Response:
    """Send JSON POST with transient-error retry and rate-limit waiting.

    The function retries on:
    - timeout and connection errors
    - HTTP 503
    - other HTTP 5xx responses
    """

    http = session or requests.Session()
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = http.post(url, json=payload, timeout=timeout_seconds)

            wait_after_response = get_rate_limit_sleep_seconds(response.headers)
            if response.status_code == 429 and wait_after_response <= 0:
                # Fallback when API does not provide explicit reset headers.
                wait_after_response = _retry_delay(attempt, base_delay_seconds, max_jitter_seconds)
            if wait_after_response > 0:
                time.sleep(wait_after_response)

            if _is_retryable_status(response.status_code):
                if attempt == max_retries:
                    response.raise_for_status()
                delay = _retry_delay(attempt, base_delay_seconds, max_jitter_seconds)
                time.sleep(delay)
                continue

            response.raise_for_status()
            return response

        except (requests.Timeout, requests.ConnectionError) as error:
            last_error = error
            if attempt == max_retries:
                break
            delay = _retry_delay(attempt, base_delay_seconds, max_jitter_seconds)
            time.sleep(delay)

        except requests.HTTPError as error:
            last_error = error
            if attempt == max_retries:
                break
            status_code = error.response.status_code if error.response is not None else 0
            if not _is_retryable_status(status_code):
                break
            delay = _retry_delay(attempt, base_delay_seconds, max_jitter_seconds)
            time.sleep(delay)

    raise RuntimeError(f"POST {url} failed after {max_retries} attempts.") from last_error
