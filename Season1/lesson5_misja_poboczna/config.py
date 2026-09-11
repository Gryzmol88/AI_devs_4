"""Settings for the side quest solution bootstrap."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SideQuestSettings(BaseSettings):
    """Load runtime settings from environment and `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    VERIFY_URL: str = Field(default="https://hub.ag3nts.org/verify")
    HUB_API_KEY: str | None = Field(default=None)
    API_KEY: str | None = Field(default=None)
    MAX_LOCAL_WAIT_SECONDS: int = Field(default=12)
    REQUEST_TIMEOUT_SECONDS: int = Field(default=30)
    RETRIES_ON_503: int = Field(default=3)
    AGGRESSIVE_MAX_ATTEMPTS: int = Field(default=120)
    AGGRESSIVE_DELAY_SECONDS: float = Field(default=1.0)
    AGGRESSIVE_ACTION: str = Field(default="getstatus")
    AGGRESSIVE_ROUTE: str = Field(default="X-01")

    @property
    def api_key(self) -> str:
        """Return API key with fallback from `HUB_API_KEY` to `API_KEY`."""

        key = self.HUB_API_KEY or self.API_KEY
        if not key:
            raise ValueError("Set HUB_API_KEY or API_KEY in environment.")
        return key
