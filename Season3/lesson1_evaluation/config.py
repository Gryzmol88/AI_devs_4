"""Konfiguracja aplikacji ładowana ze zmiennych środowiskowych."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typowana konfiguracja rozwiązania lekcji.

    Attributes:
        openrouter_api_key: Klucz API do zapytań OpenRouter.
        openrouter_base_url: Bazowy adres API OpenRouter.
        openrouter_model: Identyfikator modelu używanego w OpenRouter.
        sensors_zip_url: URL do archiwum ZIP z plikami sensorów.
        sensors_zip_path: Lokalna ścieżka zapisu archiwum ZIP.
        sensors_dir: Katalog z rozpakowanymi plikami JSON.
        output_dir: Katalog zapisu wyników pośrednich i końcowych.
        verify_url: Opcjonalny endpoint do weryfikacji odpowiedzi.
        hub_api_key: Klucz API wysyłany do endpointu weryfikacyjnego.
        task_name: Nazwa zadania oczekiwana przez API.
        llm_batch_size: Liczba notatek grupowanych w jednym żądaniu do LLM.
        llm_timeout_seconds: Limit czasu HTTP dla zapytań do LLM.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = Field(alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(default="openai/gpt-4.1-mini", alias="OPENROUTER_MODEL")

    sensors_zip_url: str = Field(
        default="https://hub.ag3nts.org/dane/sensors.zip", alias="SENSORS_ZIP_URL"
    )
    sensors_zip_path: Path = Field(
        default=Path(__file__).resolve().parent / "data" / "sensors.zip",
        alias="SENSORS_ZIP_PATH",
    )
    sensors_dir: Path = Field(
        default=Path(__file__).resolve().parent / "data" / "sensors", alias="SENSORS_DIR"
    )
    output_dir: Path = Field(
        default=Path(__file__).resolve().parent / "output", alias="OUTPUT_DIR"
    )

    verify_url: Optional[str] = Field(default=None, alias="VERIFY_URL")
    hub_api_key: Optional[str] = Field(default=None, alias="HUB_API_KEY")
    task_name: str = Field(default="evaluation", alias="TASK_NAME")

    llm_batch_size: int = Field(default=100, alias="LLM_BATCH_SIZE")
    llm_timeout_seconds: int = Field(default=45, alias="LLM_TIMEOUT_SECONDS")

    def ensure_directories(self) -> None:
        """Tworzy wymagane katalogi, jeśli jeszcze nie istnieją."""
        self.sensors_zip_path.parent.mkdir(parents=True, exist_ok=True)
        self.sensors_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
