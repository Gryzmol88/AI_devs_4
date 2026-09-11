# lesson2 - findhim (Function Calling)

Profesjonalny szkielet rozwiązania zadania `findhim` z naciskiem na:
- małą liczbę narzędzi dla LLM,
- deterministyczne liczenie odległości (Haversine),
- walidację i retry po stronie kodu,
- kontrolę pętli agenta (`max_iterations`),
- trwałe artefakty wejścia/wyjścia.

## Uruchomienie

1. Uzupełnij `.env` (w `lesson2/.env` albo w root projektu).
2. Upewnij się, że masz dane podejrzanych w:
   - `lesson2/data/input/suspects.json` lub
   - fallback: `../Data/output.json` (wynik z lesson1).
3. Uruchom:

```powershell
python main.py
```

## Najważniejsze pliki

- `src/lesson2/config.py` - konfiguracja i ścieżki.
- `src/lesson2/api/hub_client.py` - komunikacja z API Hub.
- `src/lesson2/geo.py` - Haversine + najbliższa elektrownia.
- `src/lesson2/tools/definitions.py` - JSON Schema narzędzi.
- `src/lesson2/tools/handlers.py` - wykonanie narzędzi.
- `src/lesson2/agent/loop.py` - pętla Function Calling.
- `src/lesson2/orchestrator.py` - workflow end-to-end.

