"""Konfiguracja aplikacji dla misji pobocznej lesson2."""

from pathlib import Path

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SEASON4_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


class AppSettings(BaseSettings):
    """Konfiguracja ladowana z Season4/.env."""

    model_config = SettingsConfigDict(
        env_file=str(SEASON4_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aidevs_api_key: str = Field(..., alias="AIDEVS_API_KEY")
    aidevs_task: str = Field("windpower", alias="AIDEVS_TASK")
    aidevs_verify_url: str = Field("https://hub.ag3nts.org/verify", alias="AIDEVS_VERIFY_URL")

    app_output_dir: str = Field(str(DEFAULT_OUTPUT_DIR), alias="APP_OUTPUT_DIR")
    app_timeout_seconds: int = Field(30, alias="APP_TIMEOUT_SECONDS")
    app_poll_interval_seconds: float = Field(0.3, alias="APP_POLL_INTERVAL_SECONDS")
    app_poll_timeout_seconds: int = Field(15, alias="APP_POLL_TIMEOUT_SECONDS")
    app_max_cases: int = Field(60, alias="APP_MAX_CASES")

    @model_validator(mode="after")
    def normalize_paths(self) -> "AppSettings":
        output_dir = Path(self.app_output_dir)
        if not output_dir.is_absolute():
            output_dir = (Path(__file__).resolve().parent / output_dir).resolve()
        self.app_output_dir = str(output_dir)
        return self
