"""Pydantic models for railway API request and response payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RailwayAnswer(BaseModel):
    """Represent `answer` section for railway API requests."""

    model_config = ConfigDict(extra="allow")

    action: str = Field(..., min_length=1)


class RailwayRequest(BaseModel):
    """Represent full request body expected by `/verify` for railway task."""

    model_config = ConfigDict(extra="forbid")

    apikey: str = Field(..., min_length=1)
    task: str = Field(default="railway")
    answer: RailwayAnswer


class RailwayResponse(BaseModel):
    """Represent normalized JSON response from API.

    The response schema is not fixed, so unknown fields are allowed.
    """

    model_config = ConfigDict(extra="allow")

    raw_text: str | None = None


def parse_railway_response(data: Any) -> RailwayResponse:
    """Convert arbitrary JSON-compatible object into `RailwayResponse` model."""

    if isinstance(data, dict):
        return RailwayResponse.model_validate(data)
    return RailwayResponse(raw_text=str(data))
