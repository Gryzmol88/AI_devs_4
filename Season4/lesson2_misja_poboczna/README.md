# lesson2_misja_poboczna

Skrypt do eksploracji flagi pobocznej dla `lesson2_windpower`.

## Co robi

1. Tworzy katalog runa z timestampem.
2. Laduje zestaw przypadkow "lustro/palindrom".
3. Dla kazdego case wykonuje:
   - `start`
   - `unlockCodeGenerator`
   - `getResult` (do wyniku unlock)
   - `config` (wariant testowy)
   - `getResult` (po config)
4. Zapisuje pelne trace request/response z timestampami.
5. Pokazuje logi na biezaco w terminalu oraz zapisuje je do pliku.

## Uruchomienie

```bash
python Season4/lesson2_misja_poboczna/main.py
```

## Output

W katalogu `output/<timestamp>/`:

- `step1_loaded_cases.json`
- `step2_unlock_then_mirror_config_results.json`
- `step3_unlock_then_mirror_config_summary.json`
- `final_result.txt`
- `live_run.log`
- `live_trace.ndjson`

Kazdy trace zawiera:

- `startedAt`
- `finishedAt`
- request i response JSON
- status HTTP

## Sterowanie liczba testow

Mozesz ograniczyc liczbe testowanych kombinacji przez zmienna:

- `APP_MAX_CASES` (domyslnie `180`)
