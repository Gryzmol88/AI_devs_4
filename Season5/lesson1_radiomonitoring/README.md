# lesson1_radiomonitoring

Rozwiązanie zadania `radiomonitoring` z lekcji S05E01.

## Założenia architektoniczne

- Routing danych: tekst/szum/binarka.
- Lokalna analiza binarek przed ewentualnym użyciem LLM.
- Integracja modeli przez OpenRouter.
- Konfiguracja przez Pydantic i plik `Season5/.env`.
- Każde uruchomienie zapisuje komplet rezultatów do nowego folderu:
  `output/run_<timestamp>`.

## Wymagane zmienne środowiskowe

Zdefiniuj w `Season5/.env`:

- `CENTRALA_API_KEY`
- `CENTRALA_BASE_URL` (domyślnie `https://hub.ag3nts.org`)
- `TASK_NAME` (domyślnie `radiomonitoring`)
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL` (domyślnie `https://openrouter.ai/api/v1`)
- `OPENROUTER_MODEL` (np. `openai/gpt-4.1-mini`)
- `OPENROUTER_REFERER` (opcjonalnie)
- `OPENROUTER_TITLE` (opcjonalnie)
- `REQUEST_TIMEOUT_SECONDS` (domyślnie `60`)
- `MAX_LISTEN_ITERATIONS` (domyślnie `300`)
- `USE_LLM_FOR_TRANSCRIPTIONS` (domyślnie `true`)
- `OUTPUT_BASE_DIR` (domyślnie `output`)
- `TIMESTAMP_FORMAT` (domyślnie `%Y-%m-%d_%H-%M-%S`)

## Uruchomienie

```bash
python Season5/lesson1_radiomonitoring/main.py
```

## Dodatkowe ustawienia (audio i output)

- `ENABLE_AUDIO_TRANSCRIPTION` (domyślnie `true`)
- `WHISPER_MODEL_SIZE` (domyślnie `small`)
- `WHISPER_COMPUTE_TYPE` (domyślnie `int8`)
- `OUTPUT_TASK_SUBDIR` (domyślnie `radiomonitoring`)

## Uwagi dot. audio

Jeśli Centrala zwróci załącznik audio (np. `audio/mpeg`), program:
- zapisze plik z rozszerzeniem zgodnym z MIME (np. `.mp3`),
- spróbuje wykonać lokalną transkrypcję (preferowany `faster-whisper`, fallback `openai-whisper`),
- doda fakty z transkrypcji do agregatora.

Gdy backend audio nie jest dostępny, zapisze artefakt:
- `step2_audio_transcription_unavailable_<iter>.json`
