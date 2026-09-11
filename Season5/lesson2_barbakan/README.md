# lesson2_barbakan

Minimalny szkielet rozwiazania do zadania `phonecall` z lekcji S05E02.

## Wymagane zmienne w `Season5/.env`

- `AIDEVS_API_KEY`
- `AIDEVS_VERIFY_URL` (opcjonalnie, domyslnie `https://hub.ag3nts.org/verify`)
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL` (opcjonalnie)
- `OPENROUTER_MODEL` (opcjonalnie)

### TTS/STT przez OpenRouter

- `TTS_PROVIDER` (`openrouter` albo `piper`, domyslnie `openrouter`)
- `OPENROUTER_TTS_MODEL` (opcjonalnie)
- `OPENROUTER_TTS_FALLBACK_MODELS` (opcjonalnie, lista modeli TTS rozdzielona przecinkami)
- `OPENROUTER_TTS_VOICE` (opcjonalnie, np. `Eve` dla `x-ai/grok-voice-tts-1.0`)
- `OPENROUTER_TTS_SPEED` (opcjonalnie, domyslnie `0.92`)
- `OPENROUTER_TTS_AUDIO_FORMAT` (opcjonalnie, domyslnie `mp3`)
- `OPENROUTER_TTS_MAX_RETRIES` (opcjonalnie, domyslnie `2`)
- `OPENROUTER_TTS_RETRY_BACKOFF_SECONDS` (opcjonalnie, domyslnie `1.0`)
- `OPENROUTER_STT_MODEL` (opcjonalnie)
- `OPENROUTER_STT_LANGUAGE` (opcjonalnie, domyslnie `pl`)
- `OPENROUTER_STT_AUDIO_FORMAT` (opcjonalnie, domyslnie `mp3`)

### TTS lokalny Piper (mocno zalecany dla naturalnego PL)

- `TTS_PROVIDER=piper`
- `PIPER_EXECUTABLE_PATH` (pelna sciezka do `piper.exe`)
- `PIPER_MODEL_PATH` (pelna sciezka do modelu, np. `pl_PL-mc_speech-medium.onnx`)
- `PIPER_SAMPLE_RATE` (opcjonalnie, domyslnie `22050`)
- `FFMPEG_EXECUTABLE_PATH` (pelna sciezka do `ffmpeg.exe`)

### Pozostale

- `REQUEST_TIMEOUT` (opcjonalnie)
- `DEBUG_SAVE_RAW` (opcjonalnie)

## Uruchomienie

```bash
python Season5/lesson2_barbakan/main.py
```

Wyniki posrednie i finalne trafiaja do folderu:

- `Season5/lesson2_barbakan/output/<timestamp>/`

Kazde uruchomienie tworzy osobny katalog z aktualnym timestampem.

W katalogu uruchomienia zapisywane sa tez pliki audio MP3 rozmowy:

- `stepX_outbound.mp3` (nagranie wyslane do operatora)
- `stepX_inbound.mp3` (nagranie odpowiedzi operatora, jesli dostepne)
- `stepX_hub_error_audio.mp3` (nagranie bledu zwrocone przez HUB, jesli dostepne)
