"""Konfiguracja skryptu misji pobocznej lesson3 (Take Me to Church)."""

from pathlib import Path

from pydantic import AliasChoices
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

SEASON4_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


class AppSettings(BaseSettings):
    """Przechowuje ustawienia aplikacji ładowane z pliku Season4/.env.

    Atrybuty:
        aidevs_api_key: Klucz API do endpointu verify.
        aidevs_verify_url: URL endpointu verify.
        domatowo_task: Nazwa zadania; dla tej misji wymusza `domatowo`.
        app_timeout_seconds: Timeout żądań HTTP.
        app_output_dir: Bazowy katalog na output skryptu.
    """

    model_config = SettingsConfigDict(
        env_file=str(SEASON4_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aidevs_api_key: str = Field(
        ...,
        validation_alias=AliasChoices("AIDEVS_API_KEY", "AG3NTS_API_KEY"),
    )
    aidevs_verify_url: str = Field(
        "https://hub.ag3nts.org/verify",
        validation_alias=AliasChoices("AIDEVS_VERIFY_URL", "AG3NTS_VERIFY_URL"),
    )
    domatowo_task: str = Field(
        "domatowo",
        validation_alias=AliasChoices("DOMATOWO_TASK", "AG3NTS_TASK"),
    )
    app_timeout_seconds: int = Field(
        30,
        validation_alias=AliasChoices("APP_TIMEOUT_SECONDS", "REQUEST_TIMEOUT_SECONDS"),
    )
    app_output_dir: str = Field(
        str(DEFAULT_OUTPUT_DIR),
        validation_alias=AliasChoices("APP_OUTPUT_DIR", "OUTPUT_DIR"),
    )

    @property
    def output_path(self) -> Path:
        """Wyznacza absolutną ścieżkę katalogu output.

        Returns:
            Path: Ścieżka absolutna do katalogu output.
        """

        output_dir = Path(self.app_output_dir)
        if output_dir.is_absolute():
            return output_dir
        return (Path(__file__).resolve().parent / output_dir).resolve()

