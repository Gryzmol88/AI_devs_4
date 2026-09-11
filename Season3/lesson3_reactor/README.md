# lesson3_reactor

Deterministyczne rozwiązanie zadania `reactor` bez użycia LLM w pętli sterowania.

## Kluczowe założenia

- Komendy wysyłane są do `/verify` w formacie `{"answer": {"command": "..."}}`.
- Stan planszy jest parsowany defensywnie z różnych wariantów odpowiedzi API.
- Każdy krok i wynik końcowy zapisywane są do `output/session_...`.

## Konfiguracja (`Season3/.env`)

Przykładowe zmienne używane przez moduł:

- `HUB_API_KEY`
- `HUB_VERIFY_URL` (domyślnie `https://hub.ag3nts.org/verify`)
- `REACTOR_TASK_NAME` (domyślnie `reactor`)
- `REACTOR_MAX_STEPS` (domyślnie `300`)
- `REQUEST_TIMEOUT_SECONDS`
- `RETRY_LIMIT`
- `BACKOFF_BASE_SECONDS`
- `OUTPUT_DIR_NAME`
- `OPENROUTER_API_KEY` (opcjonalnie, tylko do przyszłego wsparcia)
- `OPENROUTER_BASE_URL`
- `OPENROUTER_MODEL`

## Uruchomienie

```bash
python Season3/lesson3_reactor/main.py
```

## Artefakty

- `step000_start.json`, `stepXXX_<command>.json` - przebieg kroków
- `final_result.json`, `final_result.txt` - wynik końcowy
- `fatal_error.json` - szczegóły błędu krytycznego
