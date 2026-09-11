"""Konfiguracja aplikacji oparta o zmienne srodowiskowe."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Przechowuje konfiguracje projektu ladowana z pliku `.env`.

    Atrybuty:
        aidevs_api_key: Klucz API do centrali z zadaniami.
        aidevs_verify_url: Endpoint weryfikacyjny zadania.
        openrouter_api_key: Klucz API do OpenRouter.
        openrouter_base_url: Bazowy URL API OpenRouter.
        openrouter_model: Nazwa modelu LLM uzywanego do generowania wypowiedzi.
        tts_provider: Provider TTS (`openrouter` lub `piper`).
        openrouter_tts_model: Nazwa modelu TTS.
        openrouter_tts_fallback_models: Lista zapasowych modeli TTS rozdzielona przecinkami.
        openrouter_tts_voice: Nazwa glosu TTS zgodna z wybranym modelem.
        openrouter_tts_speed: Tempo odtwarzania TTS.
        openrouter_tts_max_retries: Maksymalna liczba ponowien dla pojedynczego modelu TTS.
        openrouter_tts_retry_backoff_seconds: Czas oczekiwania miedzy ponowieniami TTS.
        openrouter_stt_model: Nazwa modelu STT.
        openrouter_stt_language: Kod jezyka uzywany podczas transkrypcji.
        openrouter_tts_audio_format: Domyslny format audio uzywany w TTS.
        openrouter_stt_audio_format: Format audio uzywany w STT.
        piper_executable_path: Sciezka do pliku wykonywalnego Piper.
        piper_model_path: Sciezka do modelu glosu Piper.
        piper_sample_rate: Czestotliwosc probkowania wyjsciowego WAV z Piper.
        piper_length_scale: Skala dlugosci fonemow dla Piper (wieksza = wolniej).
        ffmpeg_executable_path: Sciezka do ffmpeg do konwersji WAV->MP3.
        request_timeout: Timeout zadan HTTP w sekundach.
        debug_save_raw: Flaga zapisu surowych odpowiedzi do plikow.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aidevs_api_key: SecretStr = Field(alias="AIDEVS_API_KEY")
    aidevs_verify_url: str = Field(
        default="https://hub.ag3nts.org/verify", alias="AIDEVS_VERIFY_URL"
    )

    openrouter_api_key: SecretStr = Field(alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(default="openai/gpt-4o-mini", alias="OPENROUTER_MODEL")

    tts_provider: str = Field(default="openrouter", alias="TTS_PROVIDER")
    openrouter_tts_model: str = Field(
        default="openai/gpt-4o-mini-tts", alias="OPENROUTER_TTS_MODEL"
    )
    openrouter_tts_fallback_models: str = Field(
        default="", alias="OPENROUTER_TTS_FALLBACK_MODELS"
    )
    openrouter_tts_voice: str = Field(default="alloy", alias="OPENROUTER_TTS_VOICE")
    openrouter_tts_speed: float = Field(default=0.92, alias="OPENROUTER_TTS_SPEED")
    openrouter_tts_max_retries: int = Field(default=2, alias="OPENROUTER_TTS_MAX_RETRIES")
    openrouter_tts_retry_backoff_seconds: float = Field(
        default=1.0, alias="OPENROUTER_TTS_RETRY_BACKOFF_SECONDS"
    )

    openrouter_stt_model: str = Field(default="openai/whisper-1", alias="OPENROUTER_STT_MODEL")
    openrouter_stt_language: str = Field(default="pl", alias="OPENROUTER_STT_LANGUAGE")
    openrouter_tts_audio_format: str = Field(default="mp3", alias="OPENROUTER_TTS_AUDIO_FORMAT")
    openrouter_stt_audio_format: str = Field(default="mp3", alias="OPENROUTER_STT_AUDIO_FORMAT")

    piper_executable_path: str = Field(default="", alias="PIPER_EXECUTABLE_PATH")
    piper_model_path: str = Field(default="", alias="PIPER_MODEL_PATH")
    piper_sample_rate: int = Field(default=22050, alias="PIPER_SAMPLE_RATE")
    piper_length_scale: float = Field(default=1.2, alias="PIPER_LENGTH_SCALE")
    ffmpeg_executable_path: str = Field(default="", alias="FFMPEG_EXECUTABLE_PATH")

    request_timeout: int = Field(default=60, alias="REQUEST_TIMEOUT")
    debug_save_raw: bool = Field(default=True, alias="DEBUG_SAVE_RAW")


def load_settings() -> Settings:
    """Laduje i zwraca ustawienia aplikacji.

    Returns:
        Settings: Zweryfikowany obiekt konfiguracji.
    """

    return Settings()
