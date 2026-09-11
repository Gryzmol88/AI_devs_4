"""Lokalna synteza mowy przez Piper z konwersja do MP3."""

from __future__ import annotations

import base64
import subprocess
import tempfile
from pathlib import Path

from config import Settings
from utils.logger import log_info


class PiperTtsService:
    """Udostepnia synteze mowy lokalnie przez Piper.

    Args:
        settings: Konfiguracja aplikacji z parametrami Piper i ffmpeg.
    """

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje serwis Piper i sprawdza wymagane sciezki."""

        self._settings = settings
        self._piper_exe = Path(settings.piper_executable_path).expanduser()
        self._piper_model = Path(settings.piper_model_path).expanduser()
        self._ffmpeg_exe = Path(settings.ffmpeg_executable_path).expanduser()

    def synthesize_to_base64_mp3(self, text: str) -> str:
        """Generuje MP3 z tekstu i zwraca je jako base64.

        Args:
            text: Tresc do wypowiedzenia.

        Returns:
            str: MP3 zakodowane base64.

        Raises:
            ValueError: Gdy brakuje konfiguracji sciezek do Piper lub ffmpeg.
            RuntimeError: Gdy narzedzia lokalne zwroca blad.
        """

        self._validate_paths()
        with tempfile.TemporaryDirectory(prefix="piper_tts_") as temp_dir:
            temp_path = Path(temp_dir)
            wav_path = temp_path / "speech.wav"
            mp3_path = temp_path / "speech.mp3"

            self._run_piper(text=text, wav_path=wav_path)
            self._run_ffmpeg(wav_path=wav_path, mp3_path=mp3_path)

            mp3_bytes = mp3_path.read_bytes()
            log_info(f"TTS lokalny Piper wygenerowal {len(mp3_bytes)} bajtow MP3")
            return base64.b64encode(mp3_bytes).decode("utf-8")

    def _validate_paths(self) -> None:
        """Sprawdza, czy skonfigurowane sciezki do narzedzi lokalnych istnieja."""

        if not self._settings.piper_executable_path:
            raise ValueError("Brak PIPER_EXECUTABLE_PATH w .env")
        if not self._settings.piper_model_path:
            raise ValueError("Brak PIPER_MODEL_PATH w .env")
        if not self._settings.ffmpeg_executable_path:
            raise ValueError("Brak FFMPEG_EXECUTABLE_PATH w .env")

        if not self._piper_exe.exists():
            raise ValueError(f"Nie znaleziono Piper: {self._piper_exe}")
        if not self._piper_model.exists():
            raise ValueError(f"Nie znaleziono modelu Piper: {self._piper_model}")
        if not self._ffmpeg_exe.exists():
            raise ValueError(f"Nie znaleziono ffmpeg: {self._ffmpeg_exe}")

    def _run_piper(self, text: str, wav_path: Path) -> None:
        """Uruchamia Piper i zapisuje wynik WAV.

        Args:
            text: Tresc do syntezy.
            wav_path: Sciezka pliku WAV wyjsciowego.

        Raises:
            RuntimeError: Gdy Piper zwroci kod bledu.
        """

        cmd = [
            str(self._piper_exe),
            "-m",
            str(self._piper_model),
            "-f",
            str(wav_path),
            "--sample_rate",
            str(self._settings.piper_sample_rate),
            "--length_scale",
            str(self._settings.piper_length_scale),
        ]
        result = subprocess.run(
            cmd,
            input=text,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Piper zwrocil blad. "
                f"Kod={result.returncode}, stderr={result.stderr[:500]}"
            )

    def _run_ffmpeg(self, wav_path: Path, mp3_path: Path) -> None:
        """Konwertuje WAV do MP3 przez ffmpeg.

        Args:
            wav_path: Sciezka do pliku WAV.
            mp3_path: Sciezka do pliku MP3.

        Raises:
            RuntimeError: Gdy ffmpeg zwroci kod bledu.
        """

        cmd = [
            str(self._ffmpeg_exe),
            "-y",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "3",
            str(mp3_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                "ffmpeg zwrocil blad. "
                f"Kod={result.returncode}, stderr={result.stderr[:500]}"
            )
