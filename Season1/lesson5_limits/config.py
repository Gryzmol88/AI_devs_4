"""Runtime configuration for lesson5 railway task using Pydantic Settings."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Store runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    VERIFY_URL: str = Field(default="https://hub.ag3nts.org/verify")
    HUB_API_KEY: str | None = Field(default=None)
    API_KEY: str | None = Field(default=None)
    DEFAULT_TIMEOUT_SECONDS: int = Field(default=30)
    DEFAULT_MAX_RETRIES: int = Field(default=6)
    DEFAULT_BASE_DELAY_SECONDS: float = Field(default=1.0)
    DEFAULT_MAX_JITTER_SECONDS: float = Field(default=0.4)

    @model_validator(mode="after")
    def validate_retry_params(self) -> "AppSettings":
        """Validate retry-related numeric settings."""

        if self.DEFAULT_TIMEOUT_SECONDS <= 0:
            raise ValueError("DEFAULT_TIMEOUT_SECONDS must be > 0.")
        if self.DEFAULT_MAX_RETRIES <= 0:
            raise ValueError("DEFAULT_MAX_RETRIES must be > 0.")
        if self.DEFAULT_BASE_DELAY_SECONDS < 0:
            raise ValueError("DEFAULT_BASE_DELAY_SECONDS must be >= 0.")
        if self.DEFAULT_MAX_JITTER_SECONDS < 0:
            raise ValueError("DEFAULT_MAX_JITTER_SECONDS must be >= 0.")
        return self

    @property
    def api_key(self) -> str:
        """Return hub API key from `HUB_API_KEY` or fallback `API_KEY`."""

        key = self.HUB_API_KEY or self.API_KEY
        if not key:
            raise ValueError("Missing API key. Set HUB_API_KEY or API_KEY.")
        return key
