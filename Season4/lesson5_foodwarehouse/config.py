"""Konfiguracja aplikacji oparta o Pydantic Settings."""

import json
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Przechowuje ustawienia aplikacji wczytywane z pliku .env.

    Atrybuty:
        aidevs_api_key: Klucz API do platformy zadaniowej.
        aidevs_task: Nazwa zadania przesyłana w każdym żądaniu.
        aidevs_verify_url: Adres endpointu weryfikacji.
        food4cities_url: URL z plikiem JSON zapotrzebowania miast.
        openrouter_api_key: Klucz API OpenRouter.
        openrouter_model: Nazwa modelu używanego przez OpenRouter.
        openrouter_base_url: Bazowy URL API OpenRouter.
        output_dir: Katalog na pliki wynikowe.
        request_timeout_seconds: Timeout pojedynczego żądania HTTP.
        city_destination_query: Zapytanie SQL zwracające mapowanie city -> destination.
        creator_query: Zapytanie SQL zwracające dane autora zamówień.
        signature_template_json: Szablon JSON dla signatureGenerator z placeholderami.
    """

    aidevs_api_key: str = Field(alias="AIDEVS_API_KEY")
    aidevs_task: str = Field(default="foodwarehouse", alias="AIDEVS_TASK")
    aidevs_verify_url: str = Field(
        default="https://hub.ag3nts.org/verify",
        alias="AIDEVS_VERIFY_URL",
    )
    food4cities_url: str = Field(
        default="https://hub.ag3nts.org/dane/food4cities.json",
        alias="FOOD4CITIES_URL",
    )

    openrouter_api_key: str = Field(alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        alias="OPENROUTER_MODEL",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )

    output_dir: Path = Field(default=Path("output"), alias="OUTPUT_DIR")
    request_timeout_seconds: int = Field(default=45, alias="REQUEST_TIMEOUT_SECONDS")
    city_destination_query: str = Field(default="", alias="CITY_DESTINATION_QUERY")
    creator_query: str = Field(default="", alias="CREATOR_QUERY")
    signature_template_json: str = Field(
        default='{"action":"generate","login":"{login}","birthday":"{birthday}","destination":"{destination}"}',
        alias="SIGNATURE_TEMPLATE_JSON",
    )

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def signature_template(self) -> dict[str, Any]:
        """Zwraca szablon payloadu dla signatureGenerator.

        Returns:
            Słownik z placeholderami do formatowania.
        """

        return json.loads(self.signature_template_json)
