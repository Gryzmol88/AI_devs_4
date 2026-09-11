"""Moduł konfiguracji aplikacji oparty o Pydantic Settings."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Reprezentuje wszystkie ustawienia środowiskowe aplikacji.

    Atrybuty:
        ag3nts_api_key: Klucz API wymagany przez endpoint `verify`.
        ag3nts_verify_url: Adres URL endpointu zadania.
        task_name: Nazwa zadania wysyłana w polu `task`.
        openrouter_api_key: Klucz API do OpenRouter.
        openrouter_model: Nazwa modelu OpenRouter używanego przez agenta analitycznego.
        openrouter_base_url: Bazowy URL API OpenRouter.
        openrouter_http_referer: Wartość nagłówka HTTP-Referer wysyłanego do OpenRouter.
        openrouter_x_title: Wartość nagłówka X-Title wysyłanego do OpenRouter.
        enable_intel_agent: Flaga określająca, czy uruchamiać analizę sygnału przez LLM.
        request_timeout_seconds: Limit czasu zapytań HTTP.
        output_dir: Katalog na artefakty działania.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ag3nts_api_key: str = Field(
        validation_alias=AliasChoices("AG3NTS_API_KEY", "AIDEVS_API_KEY")
    )
    ag3nts_verify_url: str = Field(
        default="https://hub.ag3nts.org/verify",
        validation_alias=AliasChoices("AG3NTS_VERIFY_URL", "AIDEVS_VERIFY_URL"),
    )
    task_name: str = Field(
        default="domatowo",
        validation_alias=AliasChoices("DOMATOWO_TASK", "AG3NTS_TASK"),
    )
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        alias="OPENROUTER_MODEL",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_http_referer: str = Field(
        default="https://localhost",
        validation_alias=AliasChoices("OPENROUTER_HTTP_REFERER", "OPENROUTER_SITE_URL"),
    )
    openrouter_x_title: str = Field(
        default="domatowo-solver",
        validation_alias=AliasChoices("OPENROUTER_X_TITLE", "OPENROUTER_APP_NAME"),
    )
    enable_intel_agent: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_INTEL_AGENT", "APP_USE_LLM_PLANNER"),
    )
    request_timeout_seconds: int = Field(
        default=40,
        validation_alias=AliasChoices("REQUEST_TIMEOUT_SECONDS", "APP_TIMEOUT_SECONDS"),
    )
    output_dir: str = Field(
        default="output",
        validation_alias=AliasChoices("OUTPUT_DIR", "APP_OUTPUT_DIR"),
    )

    @property
    def output_path(self) -> Path:
        """Zwraca bezpieczną ścieżkę katalogu wynikowego.

        Dla ścieżki względnej zwracany jest katalog osadzony w projekcie
        `Season4/lesson3_domatowo`.

        Returns:
            Path: Absolutna ścieżka katalogu output.
        """

        raw_path = Path(self.output_dir)
        if raw_path.is_absolute():
            return raw_path
        project_root = Path(__file__).resolve().parents[1]
        return project_root / raw_path

    def validate_runtime(self) -> None:
        """Waliduje kluczowe ustawienia wymagane przez to zadanie.

        Returns:
            None: Funkcja nie zwraca wartości.

        Raises:
            ValueError: Gdy nazwa taska nie odpowiada wymaganiu zadania.
        """

        if self.task_name.strip().lower() != "domatowo":
            raise ValueError(
                "Niepoprawna nazwa taska dla lesson3_domatowo. "
                "Ustaw DOMATOWO_TASK=domatowo w Season4/.env "
                "lub usuń niestandardową wartość."
            )


def load_settings() -> AppSettings:
    """Wczytuje i zwraca ustawienia aplikacji z pliku `.env`.

    Returns:
        AppSettings: Zweryfikowany obiekt konfiguracji aplikacji.
    """

    settings = AppSettings()
    settings.validate_runtime()
    return settings
