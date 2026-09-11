"""Analiza filmu pobocznego przez OpenRouter na podstawie URL.

Skrypt:
1. Pobiera plik MP4 z podanego URL.
2. Wysyła plik do transkrypcji przez endpoint kompatybilny z OpenAI API
   skonfigurowany pod OpenRouter.
3. Analizuje transkrypcję przez model czatowy z OpenRouter.
4. Zapisuje wszystkie artefakty do `output/<timestamp>/`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from glob import glob
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Any

import requests
from openai import OpenAI
from pydantic import AliasChoices
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

FLAG_PATTERN = re.compile(r"\{FLG:[^}]+\}")
DEFAULT_VIDEO_URL = "https://hub.ag3nts.org/dane/azazel_secret.mp4"


class VideoAnalysisSettings(BaseSettings):
    """Ustawienia skryptu ładowane z `Season4/.env`.

    Atrybuty:
        openrouter_api_key: Klucz OpenRouter API.
        openrouter_base_url: Bazowy URL OpenRouter (OpenAI-compatible).
        openrouter_referer: Opcjonalny HTTP-Referer dla OpenRouter.
        openrouter_title: Opcjonalny X-Title dla OpenRouter.
        transcribe_model: Model transkrypcji używany przez OpenRouter.
        analysis_model: Model analizy tekstowej używany przez OpenRouter.
        video_url: URL analizowanego filmu.
        app_timeout_seconds: Timeout żądań HTTP.
        app_output_dir: Bazowy katalog output.
        app_max_transcribe_file_mb: Maksymalny rozmiar pojedynczego pliku wysyłanego do STT.
        app_transcribe_chunk_seconds: Długość chunku audio do transkrypcji.
        app_ffmpeg_path: Opcjonalna pełna ścieżka do binarki ffmpeg.
        app_transcribe_retry_count: Liczba ponowień dla pojedynczej próby STT.
        app_transcribe_retry_delay_seconds: Początkowy czas oczekiwania między retry.
        app_transcribe_models_fallback: Lista modeli STT używana przy fallbacku.
        app_enable_local_stt_fallback: Czy włączać lokalny fallback STT.
        app_local_stt_model: Nazwa lokalnego modelu Whisper.
        app_local_stt_language: Kod języka dla lokalnego STT (np. pl, en).
        app_local_stt_device: Urządzenie dla lokalnego STT (cpu/cuda).
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = Field(..., alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_referer: str = Field(
        "https://localhost",
        validation_alias=AliasChoices("OPENROUTER_SITE_URL", "OPENROUTER_HTTP_REFERER"),
    )
    openrouter_title: str = Field(
        "lesson3-misja-poboczna-video-analysis",
        validation_alias=AliasChoices("OPENROUTER_APP_NAME", "OPENROUTER_X_TITLE"),
    )
    transcribe_model: str = Field(
        "openai/gpt-4o-mini-transcribe",
        alias="APP_TRANSCRIBE_MODEL",
    )
    analysis_model: str = Field(
        "openai/gpt-4o-mini",
        validation_alias=AliasChoices("OPENROUTER_MODEL", "APP_ANALYSIS_MODEL"),
    )
    video_url: str = Field(DEFAULT_VIDEO_URL, alias="APP_VIDEO_URL")
    app_timeout_seconds: int = Field(60, alias="APP_TIMEOUT_SECONDS")
    app_output_dir: str = Field("output", alias="APP_OUTPUT_DIR")
    app_max_transcribe_file_mb: int = Field(20, alias="APP_MAX_TRANSCRIBE_FILE_MB")
    app_transcribe_chunk_seconds: int = Field(600, alias="APP_TRANSCRIBE_CHUNK_SECONDS")
    app_ffmpeg_path: str = Field("", alias="APP_FFMPEG_PATH")
    app_transcribe_retry_count: int = Field(3, alias="APP_TRANSCRIBE_RETRY_COUNT")
    app_transcribe_retry_delay_seconds: float = Field(1.5, alias="APP_TRANSCRIBE_RETRY_DELAY_SECONDS")
    app_transcribe_models_fallback: str = Field(
        "openai/gpt-4o-mini-transcribe,openai/whisper-1",
        alias="APP_TRANSCRIBE_MODELS_FALLBACK",
    )
    app_enable_local_stt_fallback: bool = Field(True, alias="APP_ENABLE_LOCAL_STT_FALLBACK")
    app_local_stt_model: str = Field("base", alias="APP_LOCAL_STT_MODEL")
    app_local_stt_language: str = Field("pl", alias="APP_LOCAL_STT_LANGUAGE")
    app_local_stt_device: str = Field("cpu", alias="APP_LOCAL_STT_DEVICE")

    @property
    def output_path(self) -> Path:
        """Wyznacza absolutną ścieżkę katalogu output.

        Returns:
            Path: Absolutna ścieżka katalogu output.
        """

        base = Path(self.app_output_dir)
        if base.is_absolute():
            return base
        return (Path(__file__).resolve().parent / base).resolve()


def log_info(message: str) -> None:
    """Wypisuje krótki komunikat statusowy.

    Args:
        message: Treść komunikatu.

    Returns:
        None: Funkcja wykonuje wyłącznie I/O.
    """

    print(f"[lesson3_misja_poboczna] {message}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Zapisuje słownik do pliku JSON.

    Args:
        path: Ścieżka pliku.
        payload: Dane do zapisu.

    Returns:
        None: Funkcja zapisuje plik na dysku.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_ts() -> str:
    """Zwraca znacznik czasu używany w nazwie folderu runu.

    Returns:
        str: Znacznik `YYYYMMDD_HHMMSS_microseconds`.
    """

    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def download_video(video_url: str, output_file: Path, timeout_seconds: int) -> None:
    """Pobiera film MP4 z URL i zapisuje go lokalnie.

    Args:
        video_url: URL pliku wideo.
        output_file: Docelowa ścieżka pliku.
        timeout_seconds: Timeout żądania HTTP.

    Returns:
        None: Funkcja zapisuje plik MP4.
    """

    response = requests.get(video_url, timeout=timeout_seconds, stream=True)
    response.raise_for_status()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)


def resolve_ffmpeg_binary(settings: VideoAnalysisSettings) -> str:
    """Wyznacza ścieżkę do binarki ffmpeg.

    Args:
        settings: Ustawienia aplikacji.

    Returns:
        str: Polecenie/ścieżka do uruchomienia ffmpeg.

    Raises:
        RuntimeError: Gdy nie znaleziono działającej binarki ffmpeg.
    """

    candidates: list[str] = []
    if settings.app_ffmpeg_path.strip():
        candidates.append(settings.app_ffmpeg_path.strip())

    which_path = which("ffmpeg")
    if which_path:
        candidates.append(which_path)

    candidates.append(r"C:\Users\mnadr\AppData\Local\Programs\UiPath\Studio\ffmpeg\ffmpeg.exe")

    checked: list[str] = []
    for candidate in candidates:
        path_obj = Path(candidate)
        if path_obj.exists():
            return str(path_obj)
        checked.append(candidate)

    raise RuntimeError(
        "Nie znaleziono ffmpeg. Ustaw APP_FFMPEG_PATH w Season4/.env, np. "
        "C:\\Users\\mnadr\\AppData\\Local\\Programs\\UiPath\\Studio\\ffmpeg\\ffmpeg.exe. "
        f"Sprawdzone kandydaty: {checked}"
    )


def run_ffmpeg_command(command: list[str]) -> None:
    """Uruchamia polecenie ffmpeg i rzuca wyjątek przy błędzie.

    Args:
        command: Pełna komenda ffmpeg jako lista argumentów.

    Returns:
        None: Funkcja wykonuje transformację pliku.
    """

    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise RuntimeError(
            f"Blad ffmpeg (code={process.returncode}): {process.stderr.strip() or process.stdout.strip()}"
        )


def convert_video_to_wav(video_file: Path, output_wav: Path, ffmpeg_bin: str) -> None:
    """Konwertuje wideo do WAV PCM 16k mono pod transkrypcję.

    Args:
        video_file: Źródłowy plik MP4.
        output_wav: Docelowy plik WAV.
        ffmpeg_bin: Ścieżka do binarki ffmpeg.

    Returns:
        None: Funkcja zapisuje plik WAV.
    """

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg_command(
        [
            ffmpeg_bin,
            "-y",
            "-i",
            str(video_file),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_wav),
        ]
    )


def split_audio_to_chunks(
    audio_file: Path,
    chunks_dir: Path,
    chunk_seconds: int,
    ffmpeg_bin: str,
) -> list[Path]:
    """Dzieli audio na mniejsze segmenty WAV.

    Args:
        audio_file: Plik wejściowy WAV.
        chunks_dir: Katalog na segmenty.
        chunk_seconds: Długość pojedynczego segmentu.
        ffmpeg_bin: Ścieżka do binarki ffmpeg.

    Returns:
        list[Path]: Posortowana lista segmentów WAV.
    """

    chunks_dir.mkdir(parents=True, exist_ok=True)
    pattern = chunks_dir / "chunk_%03d.wav"
    run_ffmpeg_command(
        [
            ffmpeg_bin,
            "-y",
            "-i",
            str(audio_file),
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(pattern),
        ]
    )
    files = sorted(Path(path) for path in glob(str(chunks_dir / "chunk_*.wav")))
    if not files:
        raise RuntimeError("Nie utworzono chunkow audio.")
    return files


def build_openrouter_client(settings: VideoAnalysisSettings) -> OpenAI:
    """Tworzy klienta OpenAI skonfigurowanego pod OpenRouter.

    Args:
        settings: Ustawienia aplikacji.

    Returns:
        OpenAI: Klient API.
    """

    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url.rstrip("/"),
        default_headers={
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": settings.openrouter_title,
        },
    )


def transcribe_video(client: OpenAI, model: str, video_file: Path) -> dict[str, Any]:
    """Wysyła plik wideo do transkrypcji przez API zgodne z OpenAI.

    Args:
        client: Klient OpenRouter.
        model: Nazwa modelu transkrypcji.
        video_file: Ścieżka lokalna do MP4.

    Returns:
        dict[str, Any]: Odpowiedź transkrypcji jako słownik.
    """

    with video_file.open("rb") as handle:
        response = client.audio.transcriptions.create(
            model=model,
            file=handle,
            response_format="verbose_json",
        )
    return response.model_dump()


def build_transcribe_model_candidates(settings: VideoAnalysisSettings) -> list[str]:
    """Buduje listę modeli transkrypcji z fallbackiem.

    Args:
        settings: Ustawienia aplikacji.

    Returns:
        list[str]: Lista unikalnych modeli STT w kolejności prób.
    """

    models: list[str] = []
    primary = settings.transcribe_model.strip()
    if primary:
        models.append(primary)

    raw_fallback = settings.app_transcribe_models_fallback.strip()
    if raw_fallback:
        for item in raw_fallback.split(","):
            model = item.strip()
            if model:
                models.append(model)

    # Usuwa duplikaty z zachowaniem kolejności.
    unique_models: list[str] = []
    seen: set[str] = set()
    for model in models:
        if model not in seen:
            seen.add(model)
            unique_models.append(model)
    return unique_models


def transcribe_with_retry(
    client: OpenAI,
    model: str,
    file_path: Path,
    retry_count: int,
    retry_delay_seconds: float,
) -> dict[str, Any]:
    """Transkrybuje plik z ponowieniami przy błędach API.

    Args:
        client: Klient OpenRouter.
        model: Nazwa modelu transkrypcji.
        file_path: Plik audio/wideo do transkrypcji.
        retry_count: Liczba ponowień.
        retry_delay_seconds: Początkowy odstęp retry.

    Returns:
        dict[str, Any]: Odpowiedź transkrypcji jako słownik.

    Raises:
        RuntimeError: Gdy wszystkie próby zakończą się błędem.
    """

    attempts = max(1, retry_count + 1)
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            return transcribe_video(client, model, file_path)
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            errors.append(f"proba={attempt}/{attempts}: {error_text}")
            if attempt < attempts:
                sleep_seconds = retry_delay_seconds * (2 ** (attempt - 1))
                log_info(
                    f"Blad STT dla modelu={model}, proba {attempt}/{attempts}. "
                    f"Retry za {sleep_seconds:.1f}s"
                )
                time.sleep(sleep_seconds)

    raise RuntimeError(
        f"Nieudana transkrypcja dla modelu={model}. Szczegoly: {' | '.join(errors)}"
    )


def transcribe_with_model_fallback(
    client: OpenAI,
    settings: VideoAnalysisSettings,
    file_path: Path,
) -> tuple[dict[str, Any], str]:
    """Próbuje transkrypcji kolejnymi modelami STT.

    Args:
        client: Klient OpenRouter.
        settings: Ustawienia aplikacji.
        file_path: Plik do transkrypcji.

    Returns:
        tuple[dict[str, Any], str]: Wynik transkrypcji oraz model, który zadziałał.

    Raises:
        RuntimeError: Gdy wszystkie modele zawiodą.
    """

    models = build_transcribe_model_candidates(settings)
    errors: list[str] = []
    for model in models:
        log_info(f"Proba transkrypcji modelem: {model}")
        try:
            result = transcribe_with_retry(
                client=client,
                model=model,
                file_path=file_path,
                retry_count=settings.app_transcribe_retry_count,
                retry_delay_seconds=settings.app_transcribe_retry_delay_seconds,
            )
            return result, model
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{model}: {exc}")
            log_info(f"Model STT zawiodl: {model}")

    raise RuntimeError(
        "Wszystkie modele transkrypcji zawiodly: " + " || ".join(errors)
    )


def transcribe_many_files(client: OpenAI, model: str, files: list[Path]) -> dict[str, Any]:
    """Transkrybuje wiele plików audio i łączy wynik.

    Args:
        client: Klient OpenRouter.
        model: Model transkrypcji.
        files: Lista plików audio.

    Returns:
        dict[str, Any]: Połączony wynik transkrypcji.
    """

    parts: list[dict[str, Any]] = []
    full_text: list[str] = []
    for index, file_path in enumerate(files, start=1):
        log_info(f"Transkrypcja chunku {index}/{len(files)}: {file_path.name}")
        part = transcribe_video(client, model, file_path)
        parts.append(
            {
                "index": index,
                "file": str(file_path),
                "text": part.get("text", ""),
                "raw": part,
            }
        )
        full_text.append(str(part.get("text", "")))
    return {
        "text": "\n".join(full_text).strip(),
        "parts": parts,
    }


def transcribe_many_files_with_fallback(
    client: OpenAI,
    settings: VideoAnalysisSettings,
    files: list[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Transkrybuje wiele chunków z fallbackiem modeli dla każdego chunku.

    Args:
        client: Klient OpenRouter.
        settings: Ustawienia aplikacji.
        files: Lista plików chunków.

    Returns:
        tuple[dict[str, Any], list[dict[str, Any]]]:
            Połączona transkrypcja oraz metadane modeli użytych per chunk.
    """

    parts: list[dict[str, Any]] = []
    full_text: list[str] = []
    model_usage: list[dict[str, Any]] = []
    for index, file_path in enumerate(files, start=1):
        log_info(f"Transkrypcja chunku {index}/{len(files)}: {file_path.name}")
        part, used_model = transcribe_with_model_fallback(client, settings, file_path)
        parts.append(
            {
                "index": index,
                "file": str(file_path),
                "model": used_model,
                "text": part.get("text", ""),
                "raw": part,
            }
        )
        model_usage.append(
            {
                "index": index,
                "file": str(file_path),
                "model": used_model,
            }
        )
        full_text.append(str(part.get("text", "")))

    return (
        {
            "text": "\n".join(full_text).strip(),
            "parts": parts,
        },
        model_usage,
    )


def transcribe_local_whisper(
    audio_file: Path,
    settings: VideoAnalysisSettings,
) -> dict[str, Any]:
    """Transkrybuje audio lokalnie przez pakiet `whisper`.

    Args:
        audio_file: Ścieżka do pliku audio.
        settings: Ustawienia aplikacji.

    Returns:
        dict[str, Any]: Wynik transkrypcji w formacie zgodnym z pipeline.

    Raises:
        RuntimeError: Gdy brakuje zależności lub transkrypcja lokalna się nie powiedzie.
    """

    try:
        import whisper  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Brak pakietu `openai-whisper` dla lokalnego fallbacku STT. "
            "Zainstaluj: pip install openai-whisper"
        ) from exc

    # Whisper korzysta z ffmpeg wywoływanego po nazwie, więc dopinamy katalog
    # binarki do PATH bieżącego procesu.
    ffmpeg_bin = resolve_ffmpeg_binary(settings)
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir.lower() not in current_path.lower():
        os.environ["PATH"] = f"{ffmpeg_dir};{current_path}" if current_path else ffmpeg_dir

    language = settings.app_local_stt_language.strip() or None
    device = settings.app_local_stt_device.strip() or None
    model_name = settings.app_local_stt_model.strip() or "base"

    try:
        model = whisper.load_model(model_name, device=device)
        result = model.transcribe(str(audio_file), language=language, fp16=False)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Lokalna transkrypcja Whisper nieudana: {exc}") from exc

    return {
        "text": str(result.get("text", "")).strip(),
        "segments": result.get("segments", []),
        "language": result.get("language", language or "unknown"),
        "engine": "local_whisper",
        "model": model_name,
    }


def analyze_transcript(client: OpenAI, model: str, transcript_text: str) -> dict[str, Any]:
    """Analizuje transkrypcję i szuka sekretów pobocznych.

    Args:
        client: Klient OpenRouter.
        model: Model analizy tekstu.
        transcript_text: Transkrypcja filmu.

    Returns:
        dict[str, Any]: Odpowiedź modelu i znalezione flagi.
    """

    prompt = (
        "Przeanalizuj transkrypcję i wyciągnij wszystkie potencjalne sekrety.\n"
        "Szukaj zwłaszcza fragmentów wyglądających jak flagi w formacie {FLG:...},\n"
        "ukrytych adresów URL, zaszyfrowanych wskazówek oraz kolejnych kroków.\n"
        "Zwróć wynik w JSON z polami: summary, clues, urls, flags, next_steps.\n\n"
        f"TRANSKRYPCJA:\n{transcript_text}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Jesteś analitykiem CTF i OSINT."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )
    content = response.choices[0].message.content or ""
    flags = FLAG_PATTERN.findall(content) + FLAG_PATTERN.findall(transcript_text)
    return {
        "analysis_text": content,
        "flags_found": sorted(set(flags)),
        "raw_response": response.model_dump(),
    }


def run() -> dict[str, Any]:
    """Uruchamia pełną analizę filmu i zapisuje artefakty.

    Returns:
        dict[str, Any]: Podsumowanie runu.
    """

    settings = VideoAnalysisSettings()
    run_dir = settings.output_path / now_ts()
    run_dir.mkdir(parents=True, exist_ok=True)
    (settings.output_path / "latest_video_analysis_run.txt").write_text(
        str(run_dir),
        encoding="utf-8",
    )

    log_info(f"Katalog output runu: {run_dir}")
    log_info(f"Pobieranie filmu: {settings.video_url}")
    video_file = run_dir / "source_video.mp4"
    download_video(settings.video_url, video_file, settings.app_timeout_seconds)
    write_json(
        run_dir / "step1_video_download.json",
        {
            "video_url": settings.video_url,
            "video_file": str(video_file),
            "video_size_bytes": video_file.stat().st_size,
        },
    )

    log_info(f"Transkrypcja przez OpenRouter model={settings.transcribe_model}")
    client = build_openrouter_client(settings)
    ffmpeg_bin = resolve_ffmpeg_binary(settings)
    log_info(f"Uzywam ffmpeg: {ffmpeg_bin}")
    audio_file = run_dir / "audio_for_transcription.wav"
    convert_video_to_wav(video_file, audio_file, ffmpeg_bin)
    write_json(
        run_dir / "step1b_audio_prepared.json",
        {
            "audio_file": str(audio_file),
            "audio_size_bytes": audio_file.stat().st_size,
            "max_transcribe_file_mb": settings.app_max_transcribe_file_mb,
        },
    )

    max_bytes = settings.app_max_transcribe_file_mb * 1024 * 1024
    transcribe_model_used = ""
    transcribe_models_usage: list[dict[str, Any]] = []
    transcribe_source = "openrouter_audio"
    transcribe_error = ""
    try:
        if audio_file.stat().st_size <= max_bytes:
            transcription, transcribe_model_used = transcribe_with_model_fallback(
                client=client,
                settings=settings,
                file_path=audio_file,
            )
        else:
            log_info("Audio za duze, dziele na chunki")
            chunks = split_audio_to_chunks(
                audio_file=audio_file,
                chunks_dir=run_dir / "chunks",
                chunk_seconds=settings.app_transcribe_chunk_seconds,
                ffmpeg_bin=ffmpeg_bin,
            )
            transcription, transcribe_models_usage = transcribe_many_files_with_fallback(
                client=client,
                settings=settings,
                files=chunks,
            )
    except Exception as exc:  # noqa: BLE001
        transcribe_error = str(exc)
        if not settings.app_enable_local_stt_fallback:
            raise
        log_info("OpenRouter STT niedostepny, uruchamiam fallback lokalny Whisper")
        transcription = transcribe_local_whisper(audio_file, settings)
        transcribe_model_used = f"local_whisper/{settings.app_local_stt_model}"
        transcribe_source = "local_whisper"

    write_json(run_dir / "step2_transcription_raw.json", transcription)
    if transcribe_error:
        write_json(
            run_dir / "step2b_transcription_fallback_info.json",
            {
                "openrouter_stt_error": transcribe_error,
                "fallback_used": transcribe_source == "local_whisper",
                "transcribe_source": transcribe_source,
                "transcribe_model_used": transcribe_model_used,
            },
        )
    transcript_text = str(transcription.get("text", ""))
    (run_dir / "step2_transcription_text.txt").write_text(transcript_text, encoding="utf-8")

    log_info(f"Analiza transkrypcji model={settings.analysis_model}")
    analysis = analyze_transcript(client, settings.analysis_model, transcript_text)
    write_json(run_dir / "step3_analysis.json", analysis)

    summary = {
        "status": "ok",
        "video_url": settings.video_url,
        "transcribe_model": settings.transcribe_model,
        "transcribe_model_used": transcribe_model_used,
        "transcribe_models_usage": transcribe_models_usage,
        "transcribe_source": transcribe_source,
        "analysis_model": settings.analysis_model,
        "transcript_length": len(transcript_text),
        "flags_found": analysis["flags_found"],
        "run_dir": str(run_dir),
    }
    write_json(run_dir / "final_result.json", summary)
    return summary


def main() -> None:
    """Punkt wejścia skryptu.

    Returns:
        None: Funkcja uruchamia analizę i wypisuje wynik.
    """

    result = run()
    log_info(f"Wynik koncowy: {result}")


if __name__ == "__main__":
    main()
