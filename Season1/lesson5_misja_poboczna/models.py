"""Pydantic models used by the side quest bootstrap."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RailwayAnswer(BaseModel):
    """Represent the `answer` section for one railway API call."""

    model_config = ConfigDict(extra="allow")
    action: str = Field(..., min_length=1)
    route: str | None = None
    value: str | None = None


class RailwayRequest(BaseModel):
    """Represent full request payload sent to `/verify`."""

    model_config = ConfigDict(extra="forbid")
    apikey: str = Field(..., min_length=1)
    task: str = Field(default="railway")
    answer: RailwayAnswer


class RunState(BaseModel):
    """Persist current progress to resume without waiting in foreground."""

    model_config = ConfigDict(extra="ignore")
    route: str = "X-01"
    step_index: int = 0
    next_allowed_at: datetime | None = None
    last_response: dict[str, Any] = Field(default_factory=dict)
    found_flag: str | None = None
    flag_source: dict[str, Any] | None = None
    main_flag: str | None = None
    main_flag_source: dict[str, Any] | None = None
