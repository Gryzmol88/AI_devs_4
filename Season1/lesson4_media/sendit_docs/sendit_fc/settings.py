"""Configuration for sendit function-calling module based on Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SenditSettings(BaseSettings):
    """Runtime settings loaded from environment variables and optional `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    OPENROUTER_API_KEY: str = Field(...)
    HUB_API_KEY: str = Field(...)
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1")
    OPENROUTER_MODEL: str = Field(default="openai/gpt-5-mini")
    VISION_MODEL: str = Field(default="openai/gpt-4.1-mini")
