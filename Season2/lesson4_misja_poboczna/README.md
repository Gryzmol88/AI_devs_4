# lesson4_misja_poboczna

Watcher skrzynki: nasłuchuje nowych wiadomości, pobiera pełne treści i zapisuje je do folderu.

## Uruchomienie

```powershell
.venv\Scripts\python.exe Season2\lesson4_misja_poboczna\main.py --interval 5 --pages 4 --per-page 20
```

## Tylko nowe wiadomości od momentu startu

```powershell
.venv\Scripts\python.exe Season2\lesson4_misja_poboczna\main.py --skip-history
```

## Gdzie zapisuje

`Season2/lesson4_misja_poboczna/output/`

- `messages/*.json` - pełne wiadomości
- `messages/*.md` - podgląd czytelny
- `watcher_log.jsonl` - log kroków
- `state.json` - zapamiętane `seen_ids`

Przerwanie: `Ctrl+C`
