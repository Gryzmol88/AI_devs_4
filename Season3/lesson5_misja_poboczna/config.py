"""Konfiguracja aplikacji misji pobocznej lekcji 5."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Przechowuje ustawienia aplikacji ładowane z `Season3/.env`.

    Atrybuty:
        hub_api_key: Klucz API do endpointów huba.
        verify_url: Endpoint weryfikacyjny.
        maps_url: Endpoint map.
        vehicles_url: Endpoint pojazdów.
        books_url: Endpoint notatek.
        output_dir_name: Nazwa katalogu na artefakty.
        request_timeout_seconds: Timeout pojedynczego żądania.
        log_level: Poziom logowania.
        side_task_name: Jawna nazwa taska pobocznego (opcjonalna).
        side_task_candidates: Kandydaci nazw taska oddzieleni przecinkami.
        side_max_attempts: Maksymalna liczba prób wysyłki do `/verify`.
        openrouter_api_key: Klucz OpenRouter.
        openrouter_base_url: Bazowy URL OpenRouter.
        openrouter_model: Nazwa modelu OpenRouter.
        openrouter_reasoning_effort: Poziom rozumowania OpenRouter.
        use_openrouter_task_guesser: Czy aktywować zgadywanie nazwy taska przez LLM.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    hub_api_key: str = Field(alias="HUB_API_KEY")
    verify_url: str = Field(default="https://hub.ag3nts.org/verify", alias="VERIFY_URL")
    maps_url: str = Field(default="https://hub.ag3nts.org/api/maps", alias="SAVETHEM_MAPS_URL")
    vehicles_url: str = Field(default="https://hub.ag3nts.org/api/wehicles", alias="SAVETHEM_VEHICLES_URL")
    books_url: str = Field(default="https://hub.ag3nts.org/api/books", alias="SAVETHEM_BOOKS_URL")
    output_dir_name: str = Field(default="output", alias="LESSON5_SIDE_OUTPUT_DIR")
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    log_level: str = Field(default="INFO", alias="LESSON5_SIDE_LOG_LEVEL")

    side_task_name: str = Field(default="", alias="LESSON5_SIDE_TASK_NAME")
    side_task_candidates: str = Field(
        default="savethem,beavers,bobry,bonus,side,sidequest",
        alias="LESSON5_SIDE_TASK_CANDIDATES",
    )
    side_max_attempts: int = Field(default=40, alias="LESSON5_SIDE_MAX_ATTEMPTS")

    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="openai/gpt-4.1-mini", alias="OPENROUTER_MODEL")
    openrouter_reasoning_effort: str = Field(default="high", alias="OPENROUTER_REASONING_EFFORT")
    use_openrouter_task_guesser: bool = Field(default=True, alias="LESSON5_SIDE_USE_OPENROUTER_TASK_GUESSER")

    def parsed_task_candidates(self) -> list[str]:
        """Zwraca listę kandydatów nazw taska pobocznego.

        Returns:
            Lista nazw taska bez pustych elementów.
        """

        base: list[str] = []
        if self.side_task_name.strip():
            base.append(self.side_task_name.strip())
        for item in self.side_task_candidates.split(","):
            candidate = item.strip()
            if candidate and candidate not in base:
                base.append(candidate)
        return base


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ładuje i buforuje konfigurację aplikacji.

    Returns:
        Obiekt `Settings`.
    """

    return Settings()

