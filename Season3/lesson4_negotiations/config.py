"""Konfiguracja aplikacji negotiations ładowana ze środowiska i pliku .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reprezentuje ustawienia aplikacji dla zadania negotiations.

    Atrybuty:
        hub_api_key: Klucz API do wysyłania zgłoszeń do centrali.
        verify_url: Endpoint weryfikacyjny centrali.
        task_name: Nazwa zadania przekazywana do weryfikacji.
        csv_base_url: Bazowy URL z danymi CSV dla zadania.
        request_timeout_seconds: Timeout pojedynczego żądania HTTP.
        app_host: Host serwera HTTP.
        app_port: Port serwera HTTP.
        output_dir_name: Nazwa katalogu na artefakty działania.
        openrouter_api_key: Klucz API OpenRouter.
        openrouter_base_url: Bazowy adres API OpenRouter.
        openrouter_model: Identyfikator modelu OpenRouter.
        enable_llm_parser: Flaga uruchamiająca fallback parsera przez LLM.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hub_api_key: str | None = Field(default=None, alias="HUB_API_KEY")
    verify_url: str = Field(default="https://hub.ag3nts.org/verify", alias="VERIFY_URL")
    task_name: str = Field(default="negotiations", alias="NEGOTIATIONS_TASK_NAME")
    csv_base_url: str = Field(
        default="https://hub.ag3nts.org/dane/s03e04_csv/",
        alias="NEGOTIATIONS_CSV_BASE_URL",
    )

    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    app_host: str = Field(default="0.0.0.0", alias="NEGOTIATIONS_APP_HOST")
    app_port: int = Field(default=3000, alias="NEGOTIATIONS_APP_PORT")
    output_dir_name: str = Field(default="output", alias="NEGOTIATIONS_OUTPUT_DIR")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_model: str = Field(
        default="openai/gpt-4.1-mini",
        alias="OPENROUTER_MODEL",
    )
    enable_llm_parser: bool = Field(default=False, alias="NEGOTIATIONS_ENABLE_LLM_PARSER")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ładuje i buforuje konfigurację aplikacji.

    Returns:
        Obiekt `Settings` z wartościami odczytanymi z `.env` i środowiska.
    """

    return Settings()
