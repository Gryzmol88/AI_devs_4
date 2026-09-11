"""Konfiguracja aplikacji oparta o Pydantic i plik .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reprezentuje ustawienia aplikacji ładowane z pliku `.env`.

    Atrybuty:
        openrouter_api_key: Klucz API do OpenRouter.
        openrouter_model: Nazwa modelu używanego przez agenta.
        openrouter_base_url: Bazowy adres API OpenRouter.
        openrouter_max_tokens: Maksymalna liczba tokenów odpowiedzi modelu.
        hub_api_key: Klucz API do huba z zadaniami.
        hub_shell_url: Pełny URL endpointu shell API.
        hub_verify_url: Pełny URL endpointu verify API.
        max_steps: Maksymalna liczba kroków pętli agentowej.
        request_timeout_seconds: Timeout pojedynczego żądania HTTP.
        retry_limit: Maksymalna liczba ponowień przy błędach przejściowych.
        backoff_base_seconds: Bazowe opóźnienie dla mechanizmu backoff.
        output_dir_name: Nazwa katalogu na artefakty działania.
        stop_on_ban: Czy zakończyć sesję od razu po wykryciu bana VM.
        max_tool_message_chars: Maksymalna długość komunikatu narzędzia wysyłanego do modelu.
        max_history_messages: Maksymalna liczba ostatnich wiadomości trzymanych w historii.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = Field(..., alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="anthropic/claude-sonnet-4-6", alias="OPENROUTER_MODEL"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_max_tokens: int = Field(default=300, alias="OPENROUTER_MAX_TOKENS")

    hub_api_key: str = Field(..., alias="HUB_API_KEY")
    hub_shell_url: str = Field(
        default="https://hub.ag3nts.org/api/shell", alias="HUB_SHELL_URL"
    )
    hub_verify_url: str = Field(
        default="https://hub.ag3nts.org/verify", alias="HUB_VERIFY_URL"
    )

    max_steps: int = Field(default=40, alias="MAX_STEPS")
    request_timeout_seconds: float = Field(default=60.0, alias="REQUEST_TIMEOUT_SECONDS")
    retry_limit: int = Field(default=4, alias="RETRY_LIMIT")
    backoff_base_seconds: float = Field(default=1.0, alias="BACKOFF_BASE_SECONDS")

    output_dir_name: str = Field(default="output", alias="OUTPUT_DIR_NAME")
    stop_on_ban: bool = Field(default=True, alias="STOP_ON_BAN")
    max_tool_message_chars: int = Field(default=800, alias="MAX_TOOL_MESSAGE_CHARS")
    max_history_messages: int = Field(default=10, alias="MAX_HISTORY_MESSAGES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ładuje i buforuje ustawienia aplikacji.

    Zwraca:
        Obiekt `Settings` z wartościami odczytanymi z `.env` i środowiska.
    """

    return Settings()
