"""Konfiguracja aplikacji radiomonitoring oparta o Pydantic."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parent
SEASON_DIR = PROJECT_DIR.parent
ENV_PATH = SEASON_DIR / ".env"


class Settings(BaseSettings):
    """Przechowuje i waliduje ustawienia aplikacji z pliku .env."""

    centrala_api_key: str = Field(
        validation_alias=AliasChoices("AIDEVS_API_KEY", "CENTRALA_API_KEY")
    )
    centrala_base_url: str = Field(
        default="https://hub.ag3nts.org",
        validation_alias=AliasChoices("AIDEVS_VERIFY_URL", "CENTRALA_BASE_URL"),
    )
    task_name: str = Field(
        default="radiomonitoring",
        validation_alias=AliasChoices("AIDEVS_TASK", "TASK_NAME"),
    )

    openrouter_api_key: str = Field(alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(
        default="openai/gpt-4.1-mini", alias="OPENROUTER_MODEL"
    )
    openrouter_vision_model: str = Field(
        default="openai/gpt-4.1", alias="OPENROUTER_VISION_MODEL"
    )
    openrouter_referer: str = Field(
        default="",
        validation_alias=AliasChoices("OPENROUTER_SITE_URL", "OPENROUTER_REFERER"),
    )
    openrouter_title: str = Field(
        default="ai-devs-radiomonitoring",
        validation_alias=AliasChoices("OPENROUTER_APP_NAME", "OPENROUTER_TITLE"),
    )

    request_timeout_seconds: float = Field(default=60.0, alias="REQUEST_TIMEOUT_SECONDS")
    max_listen_iterations: int = Field(default=300, alias="MAX_LISTEN_ITERATIONS")
    use_llm_for_transcriptions: bool = Field(
        default=True, alias="USE_LLM_FOR_TRANSCRIPTIONS"
    )
    enable_audio_transcription: bool = Field(
        default=True, alias="ENABLE_AUDIO_TRANSCRIPTION"
    )
    whisper_model_size: str = Field(default="small", alias="WHISPER_MODEL_SIZE")
    whisper_compute_type: str = Field(default="int8", alias="WHISPER_COMPUTE_TYPE")

    output_base_dir: str = Field(
        default=str(PROJECT_DIR / "output"), alias="OUTPUT_BASE_DIR"
    )
    output_task_subdir: str = Field(default="radiomonitoring", alias="OUTPUT_TASK_SUBDIR")
    timestamp_format: str = Field(default="%Y-%m-%d_%H-%M-%S", alias="TIMESTAMP_FORMAT")

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def get_settings() -> Settings:
    """Tworzy i zwraca instancję ustawień aplikacji."""
    settings = Settings()
    if settings.centrala_base_url.rstrip("/").endswith("/verify"):
        settings.centrala_base_url = settings.centrala_base_url.rsplit("/verify", 1)[0]
    return settings
