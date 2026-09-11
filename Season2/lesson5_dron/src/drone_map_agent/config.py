"""Modele konfiguracji runtime i loader ustawień dla agenta drona (lesson5)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Wczytuje sekrety i opcje runtime z environmentu z walidacją typów.

    Ustawienia są celowo minimalne i skupione na tym jednym przepływie.
    Wartości pochodzą z:
    1) zmiennych środowiskowych procesu,
    2) `Season2/.env` przekazanego przez `_env_file`.
    """

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    openrouter_api_key: SecretStr
    hub_api_key: SecretStr

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    vision_model: str = "google/gemini-3-flash-preview"
    pilot_model: str = "openai/gpt-4o"

    task_name: str = "drone"
    verify_url: str = "https://hub.ag3nts.org/verify"
    request_timeout_seconds: int = Field(default=90, ge=10, le=300)
    max_verify_attempts: int = Field(default=8, ge=1, le=20)
    drone_docs_url: str = "https://hub.ag3nts.org/dane/drone.html"

    map_url: str | None = None
    map_url_template: str = "https://hub.ag3nts.org/data/{api_key}/drone.png"

    output_root_name: str = "output"

    def resolve_map_url(self) -> str:
        """Wyznacza finalny URL mapy z `map_url` albo z szablonu i klucza API."""

        if self.map_url:
            return self.map_url.strip()
        return self.map_url_template.format(api_key=self.hub_api_key.get_secret_value().strip())


class RuntimeConfig(BaseModel):
    """Serializowalna konfiguracja runtime bez sekretów zapisywana do artefaktów."""

    openrouter_base_url: str
    vision_model: str
    pilot_model: str
    task_name: str
    verify_url: str
    request_timeout_seconds: int
    max_verify_attempts: int
    drone_docs_url: str
    map_url: str
    output_dir: Path


def load_settings(lesson_dir: Path) -> AppSettings:
    """Wczytuje zwalidowane ustawienia z `Season2/.env` jako głównego źródła."""

    season2_env = lesson_dir.parent / ".env"
    return AppSettings(_env_file=season2_env, _env_file_encoding="utf-8")


def build_runtime_config(settings: AppSettings, lesson_dir: Path) -> RuntimeConfig:
    """Buduje zsanityzowany obiekt konfiguracji runtime do logów i reprodukcji."""

    return RuntimeConfig(
        openrouter_base_url=settings.openrouter_base_url,
        vision_model=settings.vision_model,
        pilot_model=settings.pilot_model,
        task_name=settings.task_name,
        verify_url=settings.verify_url,
        request_timeout_seconds=settings.request_timeout_seconds,
        max_verify_attempts=settings.max_verify_attempts,
        drone_docs_url=settings.drone_docs_url,
        map_url=settings.resolve_map_url(),
        output_dir=lesson_dir / settings.output_root_name,
    )
