"""Router decydujący o sposobie przetwarzania odebranego materiału."""

from __future__ import annotations

import unicodedata

from models import ListenResponse


def _normalize_text(text: str) -> str:
    """Normalizuje tekst do uproszczonej postaci ASCII.

    Args:
        text: Tekst wejściowy.

    Returns:
        Tekst bez znaków diakrytycznych i w lower-case.
    """
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def classify_signal(signal: ListenResponse) -> str:
    """Klasyfikuje odebrany sygnał do jednej z kategorii.

    Args:
        signal: Odpowiedź nasłuchu z Centrali.

    Returns:
        Jedną z wartości: 'transcription', 'attachment', 'noise', 'end', 'unknown'.
    """
    normalized_message = _normalize_text(signal.message)
    if signal.code == 101:
        return "end"
    if (
        "enough data" in normalized_message
        or "wystarczajaco" in normalized_message
        or "dostatecznie duzo materialu" in normalized_message
    ):
        return "end"
    if signal.transcription:
        return "transcription"
    if signal.attachment:
        return "attachment"
    if "noise" in normalized_message or "szum" in normalized_message:
        return "noise"
    return "unknown"
