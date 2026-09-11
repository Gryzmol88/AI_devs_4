# lesson5_misja_poboczna

Eksplorator misji pobocznej powiązanej z `savethem`, z heurystyką pod hint:
`Tam są bobry!`.

## Co robi program

1. Pobiera mapę `Skolwin` z `/api/maps`.
2. Pobiera notatki reguł z `/api/books`.
3. Pobiera parametry pojazdów z `/api/wehicles`.
4. Generuje kandydackie trasy preferujące okolice wody i północ mapy.
5. Wysyła kolejne próby do `/verify` dla kandydatów taska pobocznego.
6. Zatrzymuje się po znalezieniu flagi `{FLG:...}`.

## Uruchomienie

```powershell
cd Season3/lesson5_misja_poboczna
python main.py
```

## Output

W `output/session_run_<timestamp>/`:

- `step1_map.json`, `step1_books.json`
- `step2_vehicles.json`
- `step3_world_state.json`
- `step4_candidates.json`
- `step5_attempt_*.json`
- `final_result.json`, `final_result.txt`
- `error.json` (w razie wyjątku)

