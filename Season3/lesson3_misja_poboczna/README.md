# lesson3_misja_poboczna

Program realizuje pełną trasę robota: **tam i z powrotem**.

## Logika działania

1. Wysyła `start`.
2. Faza `to_pre_flag`: prowadzi robota do kolumny przed flaga (domyslnie 6).
3. Faza `to_start`: prowadzi robota z powrotem do kolumny 1.
4. Po każdym kroku zapisuje odpowiedź API i szuka wzorca `{FLG:...}`.
5. Wykrytą flagę wypisuje na ekran oraz zapisuje do `final_result.*`.

## Konfiguracja (`Season3/.env`)

Wymagane:

- `HUB_API_KEY`

Najważniejsze opcjonalne:

- `HUB_VERIFY_URL=https://hub.ag3nts.org/verify`
- `REACTOR_TASK_NAME=reactor`
- `REACTOR_MAX_STEPS_TOTAL=500`
- `REACTOR_MAX_WAIT_STREAK=3`
- `REACTOR_PRE_FLAG_TARGET_COL=6`
- `REACTOR_PHASE_COMPLETION_WAITS=1`
- `REACTOR_ECHO_FULL_RESPONSE=false`
- `OUTPUT_DIR_NAME=output`

## Uruchomienie

```powershell
python .\Season3\lesson3_misja_poboczna\main.py
```

## Artefakty output

- `step000_start.json`
- `stepXXX_<phase>_<command>.json`
- `final_result.json`
- `final_result.txt`
- `fatal_error.json` (przy błędzie)
