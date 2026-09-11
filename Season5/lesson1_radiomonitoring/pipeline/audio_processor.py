"""Lokalna transkrypcja audio (opcjonalna) dla załączników z nasłuchu."""

from __future__ import annotations

from pathlib import Path


class AudioTranscriptionUnavailable(RuntimeError):
    """Wyjątek sygnalizujący brak dostępnego backendu transkrypcji audio."""


def transcribe_audio_file(
    audio_path: Path,
    model_size: str = "small",
    compute_type: str = "int8",
) -> str:
    """Transkrybuje plik audio do tekstu z użyciem lokalnego backendu.

    Args:
        audio_path: Ścieżka do pliku audio.
        model_size: Nazwa modelu Whisper/Faster-Whisper.
        compute_type: Typ obliczeń dla faster-whisper (np. int8, float16).

    Returns:
        Pełna transkrypcja tekstowa.

    Raises:
        AudioTranscriptionUnavailable: Gdy żaden backend transkrypcji nie jest dostępny.
    """
    # Preferowany backend: faster-whisper (szybki i lekki).
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel(model_size, compute_type=compute_type)
        segments, _info = model.transcribe(str(audio_path), vad_filter=True)
        parts = [segment.text.strip() for segment in segments if segment.text and segment.text.strip()]
        return " ".join(parts).strip()
    except Exception:
        pass

    # Fallback: openai-whisper.
    try:
        import whisper  # type: ignore

        model = whisper.load_model(model_size)
        result = model.transcribe(str(audio_path), fp16=False)
        text = result.get("text", "") if isinstance(result, dict) else ""
        return str(text).strip()
    except Exception as error:
        raise AudioTranscriptionUnavailable(
            "Brak backendu audio (zainstaluj faster-whisper lub openai-whisper)."
        ) from error
