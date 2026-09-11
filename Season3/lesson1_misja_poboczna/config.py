"""Konfiguracja aplikacji misji pobocznej."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typowana konfiguracja dla skryptu misji pobocznej.

    Attributes:
        hint_expression: Tekst podpowiedzi z ciągiem liczb i minusów.
        decode_url: URL do pliku decode.txt zwróconego przez centralę.
        verify_url: Endpoint `/verify`.
        hub_api_key: Klucz API do centrali.
        side_task_name: Nazwa zadania dla misji pobocznej.
        output_dir: Katalog na wyniki pośrednie i końcowe.
        request_timeout_seconds: Timeout żądań HTTP.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hint_expression: str = Field(
        default="9132-1522-2306-1048-2119 hmmm... awkward :/",
        alias="SIDE_HINT_EXPRESSION",
    )
    decode_url: str = Field(
        default="https://hub.ag3nts.org/dane/decode.txt",
        alias="SIDE_DECODE_URL",
    )
    verify_url: Optional[str] = Field(default=None, alias="VERIFY_URL")
    hub_api_key: Optional[str] = Field(default=None, alias="HUB_API_KEY")
    side_task_name: str = Field(default="evaluation", alias="SIDE_TASK_NAME")
    request_timeout_seconds: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")
    output_dir: Path = Field(
        default=Path(__file__).resolve().parent / "output",
        alias="OUTPUT_DIR_SIDE",
    )

    def ensure_directories(self) -> None:
        """Tworzy katalogi wymagane do zapisu artefaktów."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
