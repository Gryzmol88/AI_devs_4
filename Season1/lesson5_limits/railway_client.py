"""Minimal API client for the `railway` task."""

from __future__ import annotations

from typing import Any

try:
    from .config import AppSettings
    from .models import RailwayAnswer, RailwayRequest, RailwayResponse, parse_railway_response
    from .retry_http import post_json_with_retry
except ImportError:
    from config import AppSettings
    from models import RailwayAnswer, RailwayRequest, RailwayResponse, parse_railway_response
    from retry_http import post_json_with_retry


def build_railway_payload(api_key: str, action: str, **answer_fields: Any) -> RailwayRequest:
    """Build validated request model for railway endpoint calls.

    Extra keyword args are added to `answer` next to `action`.
    """

    answer = RailwayAnswer(action=action, **answer_fields)
    return RailwayRequest(apikey=api_key, task="railway", answer=answer)


def call_railway_action(
    *,
    api_key: str,
    action: str,
    settings: AppSettings | None = None,
    **answer_fields: Any,
) -> RailwayResponse:
    """Call one railway action and return normalized response model."""

    cfg = settings or AppSettings()
    payload = build_railway_payload(api_key=api_key, action=action, **answer_fields)
    response = post_json_with_retry(
        url=cfg.VERIFY_URL,
        payload=payload.model_dump(),
        timeout_seconds=cfg.DEFAULT_TIMEOUT_SECONDS,
        max_retries=cfg.DEFAULT_MAX_RETRIES,
        base_delay_seconds=cfg.DEFAULT_BASE_DELAY_SECONDS,
        max_jitter_seconds=cfg.DEFAULT_MAX_JITTER_SECONDS,
    )
    try:
        return parse_railway_response(response.json())
    except Exception:
        return RailwayResponse(raw_text=response.text)
