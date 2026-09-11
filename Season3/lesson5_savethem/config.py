"""Konfiguracja aplikacji `savethem` ładowana ze środowiska i pliku `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reprezentuje ustawienia aplikacji dla zadania `savethem`.

    Atrybuty:
        hub_api_key: Klucz API przekazywany do narzędzi huba.
        verify_url: Endpoint weryfikacyjny centrali.
        savethem_task_name: Nazwa zadania przekazywana do `/verify`.
        toolsearch_url: Endpoint wyszukiwania narzędzi.
        request_timeout_seconds: Limit czasu pojedynczego żądania HTTP.
        output_dir_name: Nazwa katalogu na artefakty działania.
        openrouter_api_key: Klucz API OpenRouter.
        openrouter_base_url: Bazowy adres API OpenRouter.
        openrouter_model: Identyfikator modelu używanego przez discovery.
        openrouter_reasoning_effort: Poziom rozumowania wysyłany do API.
        discovery_iterations: Maksymalna liczba iteracji discovery.
        discovery_max_tool_calls: Maksymalna liczba wywołań narzędzi na iterację.
        default_food_budget: Domyślna liczba porcji jedzenia przy braku danych.
        default_fuel_budget: Domyślna liczba jednostek paliwa przy braku danych.
        log_level: Poziom logowania terminalowego.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    hub_api_key: str = Field(alias="HUB_API_KEY")
    verify_url: str = Field(default="https://hub.ag3nts.org/verify", alias="VERIFY_URL")
    savethem_task_name: str = Field(default="savethem", alias="SAVETHEM_TASK_NAME")
    toolsearch_url: str = Field(default="https://hub.ag3nts.org/api/toolsearch", alias="TOOLSEARCH_URL")

    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    output_dir_name: str = Field(default="output", alias="SAVETHEM_OUTPUT_DIR")
    log_level: str = Field(default="INFO", alias="SAVETHEM_LOG_LEVEL")

    openrouter_api_key: str = Field(alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="openai/gpt-4.1-mini", alias="OPENROUTER_MODEL")
    openrouter_reasoning_effort: str = Field(default="high", alias="OPENROUTER_REASONING_EFFORT")

    discovery_iterations: int = Field(default=4, alias="SAVETHEM_DISCOVERY_ITERATIONS")
    discovery_max_tool_calls: int = Field(default=10, alias="SAVETHEM_DISCOVERY_MAX_TOOL_CALLS")

    default_food_budget: int = Field(default=10, alias="SAVETHEM_DEFAULT_FOOD_BUDGET")
    default_fuel_budget: int = Field(default=10, alias="SAVETHEM_DEFAULT_FUEL_BUDGET")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ładuje i buforuje konfigurację aplikacji.

    Returns:
        Obiekt `Settings` z wartościami pobranymi ze środowiska.
    """

    return Settings()
