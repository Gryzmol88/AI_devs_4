from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionData:
    # Pelna historia wiadomosci dla konkretnej sesji operatora.
    messages: list[dict[str, Any]] = field(default_factory=list)


_SESSIONS: dict[str, SessionData] = {}


def get_session(session_id: str) -> SessionData:
    # Tworzymy sesje leniwie przy pierwszym zapytaniu.
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = SessionData()
    return _SESSIONS[session_id]


def get_messages(session_id: str) -> list[dict[str, Any]]:
    return get_session(session_id).messages


def append_messages(session_id: str, payload: list[dict[str, Any]]) -> None:
    get_session(session_id).messages.extend(payload)
