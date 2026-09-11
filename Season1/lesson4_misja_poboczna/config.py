"""Runtime settings for lesson4 side-quest probing script."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SideQuestSettings(BaseSettings):
    """Load side-quest settings from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DOC_INDEX_URL: str = Field(default="https://hub.ag3nts.org/dane/doc/index.md")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=20)
    USE_HEAD_METHOD: bool = Field(default=True)
    SAVE_DIR: str = Field(default="lesson4_misja_poboczna/output")
