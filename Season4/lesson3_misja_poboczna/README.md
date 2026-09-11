# lesson3_misja_poboczna

Skrypt realizuje wskazówkę systemową `Take Me to Church`.

## Co robi

1. Resetuje planszę (`reset`).
2. Pobiera mapę (`getMap`).
3. Znajduje pola kościoła (`searchSymbol` z `KS` + fallback z mapy).
4. Tworzy zwiadowcę.
5. Przeszukuje wszystkie pola kościoła:
   - `move`
   - `inspect`
   - `getLogs`
6. Zbiera potencjalne sekrety w formacie `{FLG:...}` z odpowiedzi API.

## Konfiguracja

Korzysta z `Season4/.env` (Pydantic):

- `AIDEVS_API_KEY`
- `AIDEVS_VERIFY_URL` (domyślnie `https://hub.ag3nts.org/verify`)
- `DOMATOWO_TASK` (domyślnie `domatowo`)
- `APP_TIMEOUT_SECONDS`
- `APP_OUTPUT_DIR`

## Uruchomienie

```bash
python main.py
```

## Analiza filmu sekretu (OpenRouter)

Skrypt pobiera film i wykonuje transkrypcję + analizę:

```bash
python analyze_secret_video.py
```

Wymagane narzędzie systemowe:

- `ffmpeg` w PATH lub ustaw `APP_FFMPEG_PATH` (skrypt konwertuje MP4 -> WAV i w razie potrzeby dzieli audio na chunki)

Wymagane / używane zmienne z `Season4/.env`:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_SITE_URL` lub `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_APP_NAME` lub `OPENROUTER_X_TITLE`
- `OPENROUTER_MODEL` (model analizy)
- `APP_TRANSCRIBE_MODEL` (model transkrypcji)
- `APP_VIDEO_URL` (opcjonalnie, domyślnie `https://hub.ag3nts.org/dane/azazel_secret.mp4`)
- `APP_MAX_TRANSCRIBE_FILE_MB` (opcjonalnie, domyślnie `20`)
- `APP_TRANSCRIBE_CHUNK_SECONDS` (opcjonalnie, domyślnie `600`)
- `APP_FFMPEG_PATH` (opcjonalnie, pełna ścieżka do `ffmpeg.exe`)
- `APP_TRANSCRIBE_MODELS_FALLBACK` (opcjonalnie, lista modeli STT po przecinku)
- `APP_TRANSCRIBE_RETRY_COUNT` (opcjonalnie, liczba retry STT)
- `APP_TRANSCRIBE_RETRY_DELAY_SECONDS` (opcjonalnie, bazowy czas retry)
- `APP_ENABLE_LOCAL_STT_FALLBACK` (opcjonalnie, `true/false`)
- `APP_LOCAL_STT_MODEL` (opcjonalnie, np. `base`, `small`)
- `APP_LOCAL_STT_LANGUAGE` (opcjonalnie, np. `pl`, `en`)
- `APP_LOCAL_STT_DEVICE` (opcjonalnie, np. `cpu`, `cuda`)

Jeśli OpenRouter STT zwraca błędy 5xx, skrypt automatycznie przełączy się na lokalną transkrypcję Whisper (gdy `APP_ENABLE_LOCAL_STT_FALLBACK=true` i pakiet `openai-whisper` jest zainstalowany).

## Dekoder sekretów

Jeśli w logach pojawia się zaszyfrowane `msg` (np. hex), użyj:

```bash
python decoder.py --input-text "tu-wklej-caly-msg"
```

Wariant automatycznego łańcucha (kolejne rundy z najlepszych kandydatów):

```bash
python decoder.py --input-file "sciezka_do_msg.txt" --auto-chain --chain-rounds 8 --branch-width 5 --depth 6
```

Wynik zapisze się do:

`output/YYYYMMDD_HHMMSS_microseconds/decoder_result.json`

## Output

Każdy run zapisuje artefakty do:

`output/YYYYMMDD_HHMMSS_microseconds/`

oraz aktualizuje:

`output/latest_run.txt`
