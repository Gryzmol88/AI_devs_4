"""Konfiguracja aplikacji dla misji pobocznej lesson4."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Reprezentuje ustawienia ładowane z `Season4/.env`.

    Atrybuty:
        ag3nts_api_key: Klucz API do endpointu verify.
        ag3nts_verify_url: URL endpointu verify.
        task_name: Nazwa taska pobocznego.
        output_dir: Katalog na artefakty uruchomienia.
        request_timeout_seconds: Timeout żądań HTTP.
        app_mode: Tryb działania: `probe`, `check_flag_ord` albo `check_flag_ord_with_main`.
        submit_done: Flaga wysyłki akcji `done` po checku.
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
        validation_alias=AliasChoices(
            "LESSON4_SIDE_TASK",
            "FILESYSTEM_SIDE_TASK",
            "AG3NTS_TASK",
        ),
    )
    output_dir: str = Field(
        default="output",
        validation_alias=AliasChoices("LESSON4_SIDE_OUTPUT_DIR", "OUTPUT_DIR"),
    )
    request_timeout_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "LESSON4_SIDE_TIMEOUT_SECONDS",
            "REQUEST_TIMEOUT_SECONDS",
            "APP_TIMEOUT_SECONDS",
        ),
    )
    app_mode: str = Field(
        default="check_flag_ord",
        validation_alias=AliasChoices("LESSON4_SIDE_MODE"),
    )
    submit_done: bool = Field(
        default=False,
        validation_alias=AliasChoices("LESSON4_SIDE_SUBMIT_DONE"),
    )

    @property
    def project_root(self) -> Path:
        """Zwraca katalog projektu `lesson4_misja_poboczna`.

        Returns:
            Path: Absolutna ścieżka katalogu projektu.
        """

        return Path(__file__).resolve().parents[1]

    @property
    def output_path(self) -> Path:
        """Zwraca katalog wynikowy jako ścieżkę absolutną.

        Returns:
            Path: Absolutna ścieżka katalogu output.
        """

        raw = Path(self.output_dir)
        if raw.is_absolute():
            return raw
        return self.project_root / raw

    def validate_runtime(self) -> None:
        """Waliduje minimalne warunki uruchomienia narzędzia.

        Returns:
            None: Funkcja nie zwraca wartości.

        Raises:
            ValueError: Gdy wymagane pola konfiguracyjne są puste.
        """

        if not self.ag3nts_api_key.strip():
            raise ValueError("Brak klucza API w Season4/.env (AIDEVS_API_KEY).")
        if not self.task_name.strip():
            raise ValueError("Brak nazwy taska pobocznego (LESSON4_SIDE_TASK).")
        if self.app_mode not in {"probe", "check_flag_ord", "check_flag_ord_with_main"}:
            raise ValueError(
                "LESSON4_SIDE_MODE musi mieć wartość 'probe', 'check_flag_ord' "
                "lub 'check_flag_ord_with_main'."
            )


def load_settings() -> AppSettings:
    """Wczytuje i waliduje ustawienia aplikacji.

    Returns:
        AppSettings: Obiekt ustawień gotowy do użycia.
    """

    settings = AppSettings()
    settings.validate_runtime()
    return settings
