# lesson3_failure

Automatyczne rozwiązanie zadania `failure` (S02E03) zgodne z podejściem:
- selekcja sygnału z dużego pliku logów,
- kompresja do limitu tokenów,
- iteracyjna poprawa na podstawie feedbacku z `/verify`.

## Konfiguracja (`Season2/.env`)

Wymagane:
- `HUB_API_KEY` (lub alternatywnie `API_KEY`)

Opcjonalne:
- `VERIFY_URL` (domyślnie `https://hub.ag3nts.org/verify`)
- `FAILURE_TASK_NAME` (domyślnie `failure`)
- `FAILURE_LOG_URL_TEMPLATE` (domyślnie `https://hub.ag3nts.org/data/{apikey}/failure.log`)
- `REQUEST_TIMEOUT_SECONDS` (domyślnie `60`)
- `FAILURE_MAX_ATTEMPTS` (domyślnie `8`)
- `FAILURE_TARGET_TOKENS` (domyślnie `1400`)
- `FAILURE_HARD_TOKEN_LIMIT` (domyślnie `1500`)
- `FAILURE_TOKEN_CHAR_RATIO` (domyślnie `3.6`)
- `FAILURE_INITIAL_EVENT_LIMIT` (domyślnie `220`)
- `FAILURE_FEEDBACK_EVENT_LIMIT` (domyślnie `40`)
- `FAILURE_OUTPUT_DIR_NAME` (domyślnie `output`)

## Uruchomienie

```powershell
python Season2\lesson3_failure\main.py
```

## Wyniki

Pliki trafiają do `Season2/lesson3_failure/output`:
- `dataset_summary.json` - statystyki wejściowego pliku logów,
- `attempt_XX_candidate.json` - metadane kandydata dla iteracji,
- `attempt_XX_logs.txt` - skondensowane logi wysyłane do centrali,
- `attempt_XX_verify.json` - odpowiedź centrali dla iteracji,
- `api_trace.jsonl` - pełny ślad request/response,
- `final_logs.txt` - ostatnia wersja logów,
- `result.json` - wynik końcowy (w tym ewentualna flaga).
