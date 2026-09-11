from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# Prefer local lesson env, fallback to project-level env after repo reorganization.
_LOCAL_ENV_PATH = BASE_DIR / ".env"
ENV_PATH = _LOCAL_ENV_PATH if _LOCAL_ENV_PATH.exists() else PROJECT_DIR / ".env"
DATA_DIR = PROJECT_DIR / "Data"
OUTPUT_PATH = DATA_DIR / "output.json"


class Settings(BaseSettings):
    """Konfiguracja aplikacji ładowana z pliku `.env` i zmiennych środowiskowych.

    Klasa przechowuje klucze API, URL danych wejściowych, endpoint weryfikacji,
    model LLM oraz rok referencyjny używany przy filtrowaniu wieku.
    """
    OPENROUTER_API_KEY: str = Field(...)
    PEOPLE_CSV_URL: str = Field(...)
    HUB_API_KEY: str | None = Field(default=None)
    API_KEY: str | None = Field(default=None)
    VERIFY_URL: str = Field("https://hub.ag3nts.org/verify")
    OPENROUTER_MODEL: str = Field("openai/gpt-4o-mini")
    REFERENCE_YEAR: int = Field(2026)

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def output_path(self) -> Path:
        return OUTPUT_PATH

    @property
    def hub_api_key(self) -> str:
        """Zwraca klucz API hubu z priorytetem `HUB_API_KEY`, fallback do `API_KEY`.

        Jeśli żaden klucz nie jest ustawiony, zgłasza `ValueError` z jasną
        informacją, co należy dodać do `.env`.
        """
        key = self.HUB_API_KEY or self.API_KEY
        if not key:
            raise ValueError("Set HUB_API_KEY (or API_KEY) in .env")
        return key

