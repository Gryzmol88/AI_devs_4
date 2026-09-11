"""Moduł konfiguracji aplikacji oparty o Pydantic Settings."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Reprezentuje ustawienia środowiskowe aplikacji.

    Atrybuty:
        ag3nts_api_key: Klucz API wymagany przez endpoint `verify`.
        ag3nts_verify_url: Adres URL endpointu zadania.
        task_name: Nazwa zadania wysyłana w polu `task`.
        natan_notes_url: URL archiwum notatek wejściowych.
        openrouter_api_key: Klucz API do OpenRouter.
        openrouter_model: Nazwa modelu OpenRouter.
        openrouter_base_url: Bazowy URL API OpenRouter.
        openrouter_http_referer: Wartość nagłówka HTTP-Referer do OpenRouter.
        openrouter_x_title: Wartość nagłówka X-Title do OpenRouter.
        openrouter_temperature: Temperatura generacji modelu.
        request_timeout_seconds: Limit czasu zapytań HTTP.
        output_dir: Katalog na artefakty działania.
        reset_filesystem_first: Flaga resetu filesystemu przed tworzeniem danych.
        use_batch_mode: Flaga wysyłki operacji jako jedna paczka.
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
        default="filesystem",
        validation_alias=AliasChoices("FILESYSTEM_TASK", "AG3NTS_TASK"),
    )
    natan_notes_url: str = Field(
        default="https://hub.ag3nts.org/dane/natan_notes.zip",
        validation_alias=AliasChoices("FILESYSTEM_NOTES_URL", "NATAN_NOTES_URL"),
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
        default="filesystem-solver",
        validation_alias=AliasChoices("OPENROUTER_X_TITLE", "OPENROUTER_APP_NAME"),
    )
    openrouter_temperature: float = Field(default=0.0, alias="OPENROUTER_TEMPERATURE")
    request_timeout_seconds: int = Field(
        default=45,
        validation_alias=AliasChoices("REQUEST_TIMEOUT_SECONDS", "APP_TIMEOUT_SECONDS"),
    )
    output_dir: str = Field(
        default="output",
        validation_alias=AliasChoices("OUTPUT_DIR", "APP_OUTPUT_DIR"),
    )
    reset_filesystem_first: bool = Field(
        default=True,
        validation_alias=AliasChoices("FILESYSTEM_RESET_FIRST"),
    )
    use_batch_mode: bool = Field(
        default=True,
        validation_alias=AliasChoices("FILESYSTEM_USE_BATCH"),
    )

    @property
    def project_root(self) -> Path:
        """Zwraca absolutną ścieżkę katalogu projektu lekcji.

        Returns:
            Path: Katalog `Season4/lesson4_filesystem`.
        """

        return Path(__file__).resolve().parents[1]

    @property
    def output_path(self) -> Path:
        """Zwraca bezpieczną ścieżkę katalogu wynikowego.

        Dla ścieżki względnej zwracany jest katalog osadzony w projekcie lekcji.

        Returns:
            Path: Absolutna ścieżka katalogu output.
        """

        raw_path = Path(self.output_dir)
        if raw_path.is_absolute():
            return raw_path
        return self.project_root / raw_path

    @property
    def prompt_extract_path(self) -> Path:
        """Zwraca ścieżkę do pliku promptu ekstrakcji danych.

        Returns:
            Path: Absolutna ścieżka do pliku promptu.
        """

        return self.project_root / "prompts" / "extract_trade_data.md"

    def validate_runtime(self) -> None:
        """Waliduje kluczowe ustawienia wymagane przez zadanie.

        Returns:
            None: Funkcja nie zwraca wartości.

        Raises:
            ValueError: Gdy konfiguracja nie spełnia podstawowych warunków.
        """

        if self.task_name.strip().lower() != "filesystem":
            raise ValueError(
                "Niepoprawna nazwa taska dla lesson4_filesystem. "
                "Ustaw FILESYSTEM_TASK=filesystem w Season4/.env "
                "lub usuń niestandardową wartość."
            )
        if not self.openrouter_api_key.strip():
            raise ValueError(
                "Brak OPENROUTER_API_KEY. Uzupełnij klucz w Season4/.env."
            )


def load_settings() -> AppSettings:
    """Wczytuje ustawienia aplikacji z pliku `.env`.

    Returns:
        AppSettings: Zweryfikowany obiekt konfiguracji.
    """

    settings = AppSettings()
    settings.validate_runtime()
    return settings

