"""Helpers for reading API rate-limit headers."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping


def _read_first_header(headers: Mapping[str, str], names: list[str]) -> str | None:
    """Return first non-empty header value from a list of candidate names."""

    for name in names:
        value = headers.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _parse_retry_after(value: str) -> float | None:
    """Parse `Retry-After` header to seconds.

    Supports both seconds and HTTP-date formats.
    Returns `None` when parsing fails.
    """

    try:
        seconds = float(value)
        return max(0.0, seconds)
    except ValueError:
        pass

    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0.0, (dt - now).total_seconds())
    except Exception:
        return None


def _parse_reset_seconds(value: str, now_epoch: float) -> float | None:
    """Parse reset header value into seconds to wait.

    The function accepts:
    - relative seconds, for example `30`
    - absolute unix epoch, for example `1710000000`
    """

    try:
        numeric = float(value)
    except ValueError:
        return None

    if numeric > now_epoch + 1:
        return max(0.0, numeric - now_epoch)
    return max(0.0, numeric)


def get_rate_limit_sleep_seconds(headers: Mapping[str, str]) -> float:
    """Return how long to sleep based on rate-limit headers.

    Priority:
    1. `Retry-After`
    2. Remaining/reset pairs (`X-RateLimit-*` or `RateLimit-*`)
    """

    retry_after = _read_first_header(headers, ["Retry-After"])
    if retry_after:
        parsed = _parse_retry_after(retry_after)
        if parsed is not None:
            return parsed

    remaining_raw = _read_first_header(
        headers,
        [
            "X-RateLimit-Remaining",
            "RateLimit-Remaining",
        ],
    )
    reset_raw = _read_first_header(
        headers,
        [
            "X-RateLimit-Reset",
            "RateLimit-Reset",
        ],
    )

    if remaining_raw is None or reset_raw is None:
        return 0.0

    try:
        remaining = int(float(remaining_raw))
    except ValueError:
        return 0.0

    if remaining > 0:
        return 0.0

    now_epoch = time.time()
    parsed_reset = _parse_reset_seconds(reset_raw, now_epoch)
    return parsed_reset if parsed_reset is not None else 0.0
