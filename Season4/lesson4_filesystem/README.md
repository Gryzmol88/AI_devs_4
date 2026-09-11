# lesson4_filesystem

Rozwiązanie zadania `filesystem` dla Season4.

## Konfiguracja

Wymagane zmienne w `Season4/.env`:

- `AIDEVS_API_KEY` lub `AG3NTS_API_KEY`
- `OPENROUTER_API_KEY`

Opcjonalne:

- `AG3NTS_VERIFY_URL` (domyślnie `https://hub.ag3nts.org/verify`)
- `FILESYSTEM_TASK` (domyślnie `filesystem`)
- `FILESYSTEM_NOTES_URL` (domyślnie `https://hub.ag3nts.org/dane/natan_notes.zip`)
- `OPENROUTER_MODEL`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_X_TITLE`
- `OPENROUTER_TEMPERATURE`
- `REQUEST_TIMEOUT_SECONDS`
- `OUTPUT_DIR`
- `FILESYSTEM_RESET_FIRST`
- `FILESYSTEM_USE_BATCH`

## Uruchomienie

```bash
python main.py
```

## Artefakty

Każde uruchomienie zapisuje dane do:

- `output/<timestamp>/step1_help.json`
- `output/<timestamp>/step2_raw_notes.txt`
- `output/<timestamp>/step3_extracted.json`
- `output/<timestamp>/step4_normalized.json`
- `output/<timestamp>/step4_actions.json`
- `output/<timestamp>/step5_reset.json` (gdy reset aktywny)
- `output/<timestamp>/step6_apply.json`
- `output/<timestamp>/final_result.json`

