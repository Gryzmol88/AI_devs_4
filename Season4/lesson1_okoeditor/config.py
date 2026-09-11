"""Moduł konfiguracji aplikacji opartej o Pydantic Settings."""

from pathlib import Path

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SEASON4_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


class AppSettings(BaseSettings):
    """Reprezentuje konfigurację aplikacji ładowaną z pliku `.env`.

    Atrybuty:
        aidevs_api_key: Klucz API używany do komunikacji z centralą.
        aidevs_task: Nazwa zadania wysyłana w polu `task`.
        aidevs_verify_url: Adres endpointu `/verify`.
        oko_login: Login do panelu webowego (opcjonalnie informacyjny).
        oko_password: Hasło do panelu webowego (opcjonalnie informacyjne).
        oko_panel_url: Adres panelu webowego.
        openrouter_api_key: Klucz API OpenRouter.
        openrouter_model: Nazwa modelu używanego przez OpenRouter.
        openrouter_base_url: Bazowy URL API OpenRouter.
        openrouter_app_name: Nazwa aplikacji przekazywana w nagłówku.
        openrouter_site_url: URL projektu przekazywany w nagłówku.
        app_output_dir: Katalog na pliki wynikowe.
        app_timeout_seconds: Timeout dla żądań HTTP.
        app_use_llm_planner: Flaga włączająca planowanie z użyciem LLM.
    """

    model_config = SettingsConfigDict(
        env_file=str(SEASON4_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aidevs_api_key: str = Field(..., alias="AIDEVS_API_KEY")
    aidevs_task: str = Field("okoeditor", alias="AIDEVS_TASK")
    aidevs_verify_url: str = Field(..., alias="AIDEVS_VERIFY_URL")

    oko_login: str = Field("Zofia", alias="OKO_LOGIN")
    oko_password: str = Field("Zofia2026!", alias="OKO_PASSWORD")
    oko_panel_url: str = Field("https://oko.ag3nts.org/", alias="OKO_PANEL_URL")

    openrouter_api_key: str = Field("", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field("openai/gpt-4.1-mini", alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(
        "https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_app_name: str = Field("lesson1-okoeditor", alias="OPENROUTER_APP_NAME")
    openrouter_site_url: str = Field("https://localhost", alias="OPENROUTER_SITE_URL")

    app_output_dir: str = Field(str(DEFAULT_OUTPUT_DIR), alias="APP_OUTPUT_DIR")
    app_timeout_seconds: int = Field(30, alias="APP_TIMEOUT_SECONDS")
    app_use_llm_planner: bool = Field(True, alias="APP_USE_LLM_PLANNER")

    @model_validator(mode="after")
    def normalize_paths(self) -> "AppSettings":
        """Normalizuje ścieżki katalogów względem katalogu projektu lekcji.

        Returns:
            Znormalizowana instancja konfiguracji.
        """

        output_dir = Path(self.app_output_dir)
        if not output_dir.is_absolute():
            output_dir = (Path(__file__).resolve().parent / output_dir).resolve()
        self.app_output_dir = str(output_dir)
        return self
