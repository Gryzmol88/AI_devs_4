import time
from typing import Any

import requests


def request_json(
    method: str,
    url: str,
    *,
    timeout: int = 30,
    retries: int = 3,
    backoff_seconds: float = 0.7,
    **kwargs: Any,
) -> Any:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.request(method=method, url=url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt == retries:
                break
            time.sleep(backoff_seconds * attempt)

    raise RuntimeError(f"Request failed after {retries} attempts: {method} {url}") from last_error

