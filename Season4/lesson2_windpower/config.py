"""Konfiguracja aplikacji dla zadania windpower."""

from pathlib import Path

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SEASON4_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


class AppSettings(BaseSettings):
    """Reprezentuje konfiguracje aplikacji ladowana z pliku .env.

    Atrybuty:
        aidevs_api_key: Klucz API do endpointu verify.
        aidevs_task: Nazwa zadania wysylana do API.
        aidevs_verify_url: Endpoint centrali z akcjami zadania.
        app_output_dir: Katalog na artefakty uruchomienia.
        app_timeout_seconds: Timeout pojedynczego requestu HTTP.
        app_poll_interval_seconds: Odstep miedzy kolejnymi pollami getResult.
        app_poll_timeout_seconds: Maksymalny czas oczekiwania na raport.
        app_service_window_seconds: Limit czasu na okno serwisowe.
        app_use_llm_assist: Flaga wlaczajaca pomocnicza analize OpenRouter.
        openrouter_api_key: Klucz API OpenRouter.
        openrouter_model: Model OpenRouter.
        openrouter_base_url: Bazowy URL OpenRouter API.
        openrouter_app_name: Nazwa aplikacji dla naglowkow OpenRouter.
        openrouter_site_url: URL projektu dla naglowkow OpenRouter.
    """

    model_config = SettingsConfigDict(
        env_file=str(SEASON4_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aidevs_api_key: str = Field(..., alias="AIDEVS_API_KEY")
    aidevs_task: str = Field("windpower", alias="AIDEVS_TASK")
    aidevs_verify_url: str = Field("https://hub.ag3nts.org/verify", alias="AIDEVS_VERIFY_URL")

    app_output_dir: str = Field(str(DEFAULT_OUTPUT_DIR), alias="APP_OUTPUT_DIR")
    app_timeout_seconds: int = Field(30, alias="APP_TIMEOUT_SECONDS")
    app_poll_interval_seconds: float = Field(0.35, alias="APP_POLL_INTERVAL_SECONDS")
    app_poll_timeout_seconds: int = Field(36, alias="APP_POLL_TIMEOUT_SECONDS")
    app_service_window_seconds: int = Field(40, alias="APP_SERVICE_WINDOW_SECONDS")
    app_use_llm_assist: bool = Field(False, alias="APP_USE_LLM_ASSIST")

    openrouter_api_key: str = Field("", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field("openai/gpt-4.1-mini", alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field("https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_app_name: str = Field("lesson2-windpower", alias="OPENROUTER_APP_NAME")
    openrouter_site_url: str = Field("https://localhost", alias="OPENROUTER_SITE_URL")

    @model_validator(mode="after")
    def normalize_paths(self) -> "AppSettings":
        """Normalizuje sciezke katalogu output.

        Returns:
            Znormalizowana instancja konfiguracji.
        """

        output_dir = Path(self.app_output_dir)
        if not output_dir.is_absolute():
            output_dir = (Path(__file__).resolve().parent / output_dir).resolve()
        self.app_output_dir = str(output_dir)
        if self.aidevs_task.strip().lower() != "windpower":
            raise ValueError(
                "Niepoprawny AIDEVS_TASK dla lesson2_windpower. "
                "Ustaw AIDEVS_TASK=windpower w Season4/.env."
            )
        verify_url = self.aidevs_verify_url.strip().lower()
        if not verify_url.endswith("/verify"):
            raise ValueError(
                "Niepoprawny AIDEVS_VERIFY_URL. Oczekiwany endpoint powinien konczyc sie na /verify."
            )
        return self
