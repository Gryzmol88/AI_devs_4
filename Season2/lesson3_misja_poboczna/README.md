# lesson3_misja_poboczna

Solver pod hint:

`Tokeny złych odpowiedzi to znaki`

Tryb pracy:
- bierze pełne logi z `lesson3_failure/output/final_logs.txt`,
- generuje kontrolowane mutacje (celowo złe warianty),
- wysyła je do `/verify` dla tasku `failure`,
- zbiera potencjalne znaki z odpowiedzi błędnych,
- buduje kandydatów flagi pobocznej.

## Uruchomienie

```powershell
python Season2\lesson3_misja_poboczna\main.py
```

## Konfiguracja (`Season2/.env` lub root `.env`)

- `SIDE_TASK_NAME=failure`
- `SIDE_ANSWER_FIELD=logs`
- `SIDE_BASE_LOGS_PATH=Season2/lesson3_failure/output/final_logs.txt`
- `SIDE_MAX_ATTEMPTS=24`
- `SIDE_STOP_ON_FLAG=true`
- `VERIFY_URL`
- `HUB_API_KEY` lub `API_KEY`

## Output

- `output/submit_trace.jsonl` - log każdej próby (wariant, kod, message, znaki)
- `output/result.json` - podsumowanie i kandydaci flag
