"""Konfiguracja aplikacji misji pobocznej oparta o Pydantic i plik .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reprezentuje ustawienia aplikacji ladowane z pliku `.env`.

    Atrybuty:
        hub_api_key: Klucz API do huba z zadaniami.
        hub_shell_url: Pelny URL endpointu shell API.
        hub_verify_url: Pelny URL endpointu verify API.
        max_steps: Maksymalna liczba krokow uruchomienia.
        request_timeout_seconds: Timeout pojedynczego zadania HTTP.
        retry_limit: Maksymalna liczba ponowien przy bledach przejsciowych.
        backoff_base_seconds: Bazowe opoznienie dla mechanizmu backoff.
        output_dir_name: Nazwa katalogu na artefakty dzialania.
        stop_on_ban: Czy zakonczyc sesje od razu po wykryciu bana VM.
        side_task_name: Nazwa zadania do endpointu `/verify`.
        side_task_binary_path: Sciezka programu/binarki uruchamianej w VM.
        side_task_answer_key: Klucz pola odpowiedzi dla verify.
        side_task_auto_submit: Czy automatycznie wysylac wynik do verify.
        side_task_success_regex: Regex wykrywajacy poprawny kod.
        side_task_pre_commands: Polecenia wstepne rozdzielone przecinkami.
        capture_file_contents: Czy zapisywac zawartosc napotkanych plikow.
        capture_max_files: Maksymalna liczba plikow do zrzutu tresci.
        capture_max_chars: Maksymalna liczba znakow na jeden plik.
        discover_full_fs: Czy skanowac caly filesystem (bez sciezek zabronionych).
        discover_max_dirs: Maksymalna liczba katalogow do przeskanowania.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hub_api_key: str = Field(..., alias="HUB_API_KEY")
    hub_shell_url: str = Field(
        default="https://hub.ag3nts.org/api/shell", alias="HUB_SHELL_URL"
    )
    hub_verify_url: str = Field(
        default="https://hub.ag3nts.org/verify", alias="HUB_VERIFY_URL"
    )

    max_steps: int = Field(default=40, alias="MAX_STEPS")
    request_timeout_seconds: float = Field(default=60.0, alias="REQUEST_TIMEOUT_SECONDS")
    retry_limit: int = Field(default=4, alias="RETRY_LIMIT")
    backoff_base_seconds: float = Field(default=1.0, alias="BACKOFF_BASE_SECONDS")

    output_dir_name: str = Field(default="output", alias="OUTPUT_DIR_NAME")
    stop_on_ban: bool = Field(default=True, alias="STOP_ON_BAN")
    side_task_name: str = Field(default="lesson2_side", alias="SIDE_TASK_NAME")
    side_task_binary_path: str = Field(
        default="/opt/firmware/cooler/cooler.bin",
        alias="SIDE_TASK_BINARY_PATH",
    )
    side_task_answer_key: str = Field(default="confirmation", alias="SIDE_TASK_ANSWER_KEY")
    side_task_auto_submit: bool = Field(default=True, alias="SIDE_TASK_AUTO_SUBMIT")
    side_task_success_regex: str = Field(
        default=r"ECCS-[A-Za-z0-9]{40}",
        alias="SIDE_TASK_SUCCESS_REGEX",
    )
    side_task_pre_commands: str = Field(
        default=(
            "help,ls /,ls /home,ls /home/operator,ls /home/operator/notes,"
            "ls /opt,ls /opt/firmware,ls /opt/firmware/cooler,"
            "cat /home/operator/notes/pass.txt,cat /home/operator/.bash_history"
        ),
        alias="SIDE_TASK_PRE_COMMANDS",
    )
    capture_file_contents: bool = Field(default=True, alias="CAPTURE_FILE_CONTENTS")
    capture_max_files: int = Field(default=80, alias="CAPTURE_MAX_FILES")
    capture_max_chars: int = Field(default=40000, alias="CAPTURE_MAX_CHARS")
    discover_full_fs: bool = Field(default=True, alias="DISCOVER_FULL_FS")
    discover_max_dirs: int = Field(default=500, alias="DISCOVER_MAX_DIRS")

    def get_pre_commands(self) -> list[str]:
        """Zwraca liste komend wstepnych odczytana z konfiguracji.

        Returns:
            Lista komend shell wykonywanych przed faza uruchomien binarki.
        """

        commands = [item.strip() for item in self.side_task_pre_commands.split(",")]
        return [item for item in commands if item]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Laduje i buforuje ustawienia aplikacji.

    Zwraca:
        Obiekt `Settings` z wartosciami odczytanymi z `.env` i srodowiska.
    """

    return Settings()
