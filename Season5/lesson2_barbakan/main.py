"""Punkt wejscia programu realizujacego zadanie phonecall."""

from datetime import datetime
from pathlib import Path

from clients.hub_client import HubClient
from clients.openrouter_client import OpenRouterClient
from config import load_settings
from services.audio_service import AudioService
from services.dialog_manager import DialogManager
from services.speech_style_service import SpeechStyleService
from utils.logger import log_error, log_info


def main() -> None:
    """Uruchamia proces rozmowy i zapisuje wyniki do folderu `output/<timestamp>`.

    Efekty uboczne:
        - Wysyla zadania HTTP do OpenRouter i centrali zadania.
        - Zapisuje pliki diagnostyczne i finalne w katalogu `output/<timestamp>`.
        - Wypisuje status dzialania do terminala.
    """

    log_info("Ladowanie konfiguracji z pliku .env...")
    settings = load_settings()

    log_info(f"Wybrany model OpenRouter: {settings.openrouter_model}")
    log_info(f"Wybrany provider TTS: {settings.tts_provider}")

    hub_client = HubClient(settings=settings)
    or_client = OpenRouterClient(settings=settings)
    audio_service = AudioService(settings=settings, client=or_client)
    speech_style = SpeechStyleService(client=or_client)

    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).resolve().parent / "output" / run_timestamp
    log_info(f"Katalog output dla tego uruchomienia: {output_dir}")
    manager = DialogManager(
        hub_client=hub_client,
        audio_service=audio_service,
        speech_style=speech_style,
        output_dir=output_dir,
    )

    log_info("Start procesu realizacji zadania phonecall...")
    final_response = manager.run()
    log_info(f"Zakonczono proces. Wynik zapisany do: {output_dir}")
    log_info(f"Klucze finalnej odpowiedzi: {', '.join(final_response.raw.keys())}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log_error(f"Wystapil blad krytyczny: {exc}")
        raise
