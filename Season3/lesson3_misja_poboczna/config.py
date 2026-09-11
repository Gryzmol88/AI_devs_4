"""Konfiguracja programu "tam i z powrotem" dla lesson3_misja_poboczna."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reprezentuje ustawienia aplikacji ładowane z `Season3/.env`.

    Atrybuty:
        hub_api_key: Klucz API do huba.
        hub_verify_url: Endpoint `/verify` używany do komend robota.
        reactor_task_name: Nazwa zadania wysyłana jako `task`.
        output_dir_name: Nazwa katalogu z artefaktami działania.
        request_timeout_seconds: Timeout pojedynczego żądania HTTP.
        retry_limit: Maksymalna liczba ponowień błędów przejściowych.
        backoff_base_seconds: Bazowe opóźnienie mechanizmu backoff.
        max_steps_total: Maksymalna liczba kroków po `start`.
        max_wait_streak: Maksymalna liczba kolejnych `wait` preferowana przez heurystykę.
        pre_flag_target_col: Kolumna docelowa fazy pierwszej (przed polem flagi).
        phase_completion_waits: Dodatkowe komendy `wait` po osiągnięciu celu i po powrocie.
        echo_full_response: Czy wypisywać pełną odpowiedź API do terminala.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hub_api_key: str = Field(..., alias="HUB_API_KEY")
    hub_verify_url: str = Field(default="https://hub.ag3nts.org/verify", alias="HUB_VERIFY_URL")
    reactor_task_name: str = Field(default="reactor", alias="REACTOR_TASK_NAME")

    output_dir_name: str = Field(default="output", alias="OUTPUT_DIR_NAME")
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    retry_limit: int = Field(default=4, alias="RETRY_LIMIT")
    backoff_base_seconds: float = Field(default=0.7, alias="BACKOFF_BASE_SECONDS")

    max_steps_total: int = Field(default=500, alias="REACTOR_MAX_STEPS_TOTAL")
    max_wait_streak: int = Field(default=3, alias="REACTOR_MAX_WAIT_STREAK")
    pre_flag_target_col: int = Field(default=6, alias="REACTOR_PRE_FLAG_TARGET_COL")
    phase_completion_waits: int = Field(default=1, alias="REACTOR_PHASE_COMPLETION_WAITS")
    echo_full_response: bool = Field(default=False, alias="REACTOR_ECHO_FULL_RESPONSE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ładuje i buforuje ustawienia aplikacji.

    Returns:
        Obiekt `Settings` z wartościami odczytanymi z `.env`.
    """

    return Settings()
