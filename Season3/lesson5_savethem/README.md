# lesson5_savethem

Rozwiązanie zadania `savethem` dla Season3 Lesson 5.

## Co robi program

1. Ładuje konfigurację przez Pydantic z `Season3/.env`.
2. Odkrywa narzędzia i dane przez `toolsearch` oraz wykryte endpointy.
3. Normalizuje mapę, zasady i parametry pojazdów.
4. Wylicza trasę solverem deterministycznym z ograniczeniami paliwa i jedzenia.
5. Wysyła odpowiedź do `/verify`.
6. Zapisuje pełny przebieg do `output/session_<timestamp>`.

## Uruchomienie

```powershell
cd Season3/lesson5_savethem
python main.py
```

## Najważniejsze artefakty output

- `step0_start.json` - konfiguracja techniczna sesji.
- `step1_discovery_result.json` - surowe dane z discovery.
- `step2_normalized.json` - dane po normalizacji.
- `step3_solution.json` - wynik solvera.
- `step4_verify_response.json` - odpowiedź `/verify`.
- `final_result.json` - finalny payload i wynik.
- `error.json` - szczegóły błędu (gdy wystąpi).

