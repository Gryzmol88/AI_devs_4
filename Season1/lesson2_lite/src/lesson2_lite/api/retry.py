import time
from typing import Any

import requests
from requests import HTTPError


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 3,
) -> Any:
    """
    Wysyla zapytanie HTTP z retry i zwraca odpowiedz JSON, aby caly kod API mial
    jednolita obsluge bledow i odpornosc na chwilowe problemy sieci.
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                json=payload,
                params=params,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            try:
                return response.json()
            except Exception:  # noqa: BLE001
                return {"raw_text": response.text.strip()}
        except HTTPError as error:
            status = error.response.status_code if error.response is not None else "unknown"
            body = ""
            if error.response is not None:
                body = error.response.text[:300].replace("\n", " ")
            last_error = RuntimeError(f"HTTP {status} for {method} {url} | body={body}")
            if attempt == retries:
                break
            time.sleep(0.6 * attempt)
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt == retries:
                break
            time.sleep(0.6 * attempt)

    raise RuntimeError(f"Request failed after {retries} attempts: {method} {url}") from last_error

