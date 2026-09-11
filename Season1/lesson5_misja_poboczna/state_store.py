"""Helpers for reading and writing local side quest state."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from .models import RunState
except ImportError:
    from models import RunState


def load_state(path: Path) -> RunState:
    """Load run state from JSON file or return default state when missing."""

    if not path.exists():
        return RunState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunState.model_validate(data)


def save_state(path: Path, state: RunState) -> None:
    """Write run state JSON so next run can continue from the same step."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
