"""Warstwa pomocnicza do konwersji tekst<->audio przez wybrany provider."""

from clients.openrouter_client import OpenRouterClient
from config import Settings
from services.tts_local_piper import PiperTtsService
from utils.logger import log_info


class AudioService:
    """Udostepnia uproszczony interfejs syntezy i transkrypcji audio.

    Args:
        settings: Konfiguracja aplikacji.
        client: Klient OpenRouter obslugujacy endpointy audio.
    """

    def __init__(self, settings: Settings, client: OpenRouterClient) -> None:
        """Inicjalizuje serwis audio i provider TTS."""

        self._settings = settings
        self._client = client
        self._piper = PiperTtsService(settings=settings)

    def synthesize_to_base64(self, text: str) -> str:
        """Zamienia tekst na audio base64.

        Args:
            text: Tresc komunikatu do wypowiedzenia.

        Returns:
            str: Nagranie audio zakodowane base64.
        """

        provider = self._settings.tts_provider.strip().lower()
        if provider == "piper":
            log_info("TTS provider: piper (lokalny)")
            return self._piper.synthesize_to_base64_mp3(text)

        log_info("TTS provider: openrouter")
        return self._client.text_to_speech(text)

    def transcribe_from_base64(self, audio_base64: str) -> str:
        """Zamienia audio base64 na tekst.

        Args:
            audio_base64: Nagranie audio zakodowane base64.

        Returns:
            str: Tekst po transkrypcji.
        """

        return self._client.speech_to_text(audio_base64)
