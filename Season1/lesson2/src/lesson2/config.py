from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
LESSON_DIR = BASE_DIR.parents[2]
ROOT_DIR = LESSON_DIR.parent

_LOCAL_ENV = LESSON_DIR / ".env"
ENV_PATH = _LOCAL_ENV if _LOCAL_ENV.exists() else ROOT_DIR / ".env"


class Settings(BaseSettings):
    OPENROUTER_API_KEY: str = Field(...)
    HUB_API_KEY: str | None = Field(default=None)
    API_KEY: str | None = Field(default=None)
    VERIFY_URL: str = Field(default="https://hub.ag3nts.org/verify")
    HUB_BASE_URL: str = Field(default="https://hub.ag3nts.org")
    OPENROUTER_MODEL: str = Field(default="openai/gpt-4o-mini")
    MAX_ITERATIONS: int = Field(default=15)
    DISTANCE_THRESHOLD_KM: float = Field(default=10.0)

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def hub_api_key(self) -> str:
        key = self.HUB_API_KEY or self.API_KEY
        if not key:
            raise ValueError("Set HUB_API_KEY (or API_KEY) in .env")
        return key

    @property
    def data_dir(self) -> Path:
        return LESSON_DIR / "data"

    @property
    def suspects_path(self) -> Path:
        return self.data_dir / "input" / "suspects.json"

    @property
    def fallback_suspects_path(self) -> Path:
        return ROOT_DIR / "Data" / "output.json"

    @property
    def plants_cache_path(self) -> Path:
        return self.data_dir / "input" / "power_plants.json"

    @property
    def report_output_path(self) -> Path:
        return self.data_dir / "output" / "candidate_report.json"

    @property
    def verify_output_path(self) -> Path:
        return self.data_dir / "output" / "verify_response.json"

    @property
    def trace_path(self) -> Path:
        return self.data_dir / "logs" / "agent_trace.jsonl"

    @property
    def locations_url(self) -> str:
        return f"{self.HUB_BASE_URL}/data/{self.hub_api_key}/findhim_locations.json"

