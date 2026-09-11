"""Konfiguracja eksploratora misji pobocznej dla lesson4."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reprezentuje ustawienia aplikacji misji pobocznej lesson4.

    Atrybuty:
        hub_api_key: Klucz API do komunikacji z centralą.
        verify_url: Adres endpointu `/verify`.
        task_name: Nazwa zadania głównego powiązanego z misją poboczną.
        input_base_url: Bazowy URL z danymi wejściowymi zadania.
        request_timeout_seconds: Timeout pojedynczego żądania HTTP.
        output_dir_name: Nazwa katalogu zapisu artefaktów.
        enable_verify_exploration: Flaga uruchamiająca aktywne próby payloadów.
        max_payload_attempts: Maksymalna liczba payloadów wysyłanych do `/verify`.
        side_tool_url: Publiczny URL narzędzia z misji głównej.
        check_poll_retries: Liczba dodatkowych prób `action=check` po zgłoszeniu `tools`.
        check_poll_delay_seconds: Odstęp między kolejnymi próbami `check`.
        manual_description_file: Nazwa pliku z ręcznie edytowanym opisem toola.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hub_api_key: str = Field(..., alias="HUB_API_KEY")
    verify_url: str = Field(default="https://hub.ag3nts.org/verify", alias="VERIFY_URL")
    task_name: str = Field(default="negotiations", alias="NEGOTIATIONS_TASK_NAME")
    input_base_url: str = Field(
        default="https://hub.ag3nts.org/dane/s03e04_csv/",
        alias="NEGOTIATIONS_CSV_BASE_URL",
    )
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")
    output_dir_name: str = Field(default="output", alias="LESSON4_SIDE_OUTPUT_DIR")
    enable_verify_exploration: bool = Field(default=True, alias="LESSON4_SIDE_ENABLE_VERIFY_EXPLORATION")
    max_payload_attempts: int = Field(default=40, alias="LESSON4_SIDE_MAX_PAYLOAD_ATTEMPTS")
    side_tool_url: str = Field(
        default="https://nontheoretic-unsublimed-aundrea.ngrok-free.dev/api/find-cities",
        alias="LESSON4_SIDE_TOOL_URL",
    )
    check_poll_retries: int = Field(default=8, alias="LESSON4_SIDE_CHECK_POLL_RETRIES")
    check_poll_delay_seconds: float = Field(default=6.0, alias="LESSON4_SIDE_CHECK_POLL_DELAY_SECONDS")
    manual_description_file: str = Field(
        default="manual_tool_description.txt",
        alias="LESSON4_SIDE_MANUAL_DESCRIPTION_FILE",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ładuje i buforuje konfigurację aplikacji.

    Returns:
        Wczytany obiekt `Settings`.
    """

    return Settings()
