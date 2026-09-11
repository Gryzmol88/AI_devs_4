"""Konfiguracja aplikacji reactor ładowana ze zmiennych środowiskowych."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reprezentuje ustawienia aplikacji reactor.

    Atrybuty:
        hub_api_key: Klucz API do huba z zadaniami.
        hub_verify_url: Endpoint przyjmujący komendy i zwracający stan planszy.
        task_name: Nazwa zadania przekazywana do `/verify`.
        max_steps: Maksymalna liczba kroków po komendzie `start`.
        request_timeout_seconds: Timeout pojedynczego żądania HTTP.
        retry_limit: Maksymalna liczba ponowień żądania.
        backoff_base_seconds: Bazowe opóźnienie backoff między próbami.
        output_dir_name: Nazwa katalogu na artefakty działania.
        openrouter_api_key: Opcjonalny klucz API OpenRouter do przyszłej analizy LLM.
        openrouter_base_url: Bazowy URL OpenRouter.
        openrouter_model: Domyślny model OpenRouter używany przez warstwę opcjonalną.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hub_api_key: str = Field(..., alias="HUB_API_KEY")
    hub_verify_url: str = Field(
        default="https://hub.ag3nts.org/verify",
        alias="HUB_VERIFY_URL",
    )
    task_name: str = Field(default="reactor", alias="REACTOR_TASK_NAME")

    max_steps: int = Field(default=300, alias="REACTOR_MAX_STEPS")
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    retry_limit: int = Field(default=4, alias="RETRY_LIMIT")
    backoff_base_seconds: float = Field(default=0.7, alias="BACKOFF_BASE_SECONDS")
    output_dir_name: str = Field(default="output", alias="OUTPUT_DIR_NAME")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_model: str = Field(
        default="openai/gpt-4.1-mini",
        alias="OPENROUTER_MODEL",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ładuje i buforuje konfigurację aplikacji.

    Returns:
        Obiekt `Settings` z wartościami odczytanymi z `.env` i środowiska.
    """

    return Settings()
