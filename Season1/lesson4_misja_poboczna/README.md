# lesson4_misja_poboczna

Starter skryptu do misji pobocznej z tropem:
"Mysleli, ze to usuneli, ale to zostalo w mojej GLOWIE".

Skrypt:
- pobiera `index.md`,
- szuka linkow i wersji historycznych,
- probuje kandydatow typu `zalacznik-I.*` oraz `index` z parametrami wersji,
- wykonuje `HEAD` i `GET` dla kazdego kandydata,
- skanuje naglowki i tresc pod `{FLG:...}`.

## Uruchomienie

```bash
python lesson4_misja_poboczna/main.py
```

Wynik:
- `lesson4_misja_poboczna/output/probe_results.json`

## Konfiguracja (.env)

- `DOC_INDEX_URL`
- `REQUEST_TIMEOUT_SECONDS`
- `USE_HEAD_METHOD`
- `SAVE_DIR`
