# lesson3_domatowo

Solver zadania `domatowo` z lekcji S04E03.

## Założenia

- Program korzysta z API: `https://hub.ag3nts.org/verify`.
- Konfiguracja jest ładowana z pliku `Season4/.env` przez Pydantic.
- Integracja z modelem działa przez OpenRouter (opcjonalna warstwa analizy sygnału).
- Wyniki pośrednie i końcowe są zapisywane do folderu `output`.

## Minimalne zmienne `.env` (w `Season4/.env`)

```env
AG3NTS_API_KEY=twoj_klucz
AG3NTS_VERIFY_URL=https://hub.ag3nts.org/verify
OPENROUTER_API_KEY=twoj_openrouter_key
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://localhost
OPENROUTER_X_TITLE=domatowo-solver
ENABLE_INTEL_AGENT=true
REQUEST_TIMEOUT_SECONDS=40
OUTPUT_DIR=output
```

## Uruchomienie

```bash
python main.py
```

## Co zapisuje program

- Każde uruchomienie tworzy katalog: `output/YYYYMMDD_HHMMSS_microseconds/`
- Przykładowe pliki:
  - `step1_help.json`
  - `step1b_action_cost.json`
  - `step2_map.json`
  - `step3_intel.json`
  - `step3b_search_b3.json`
  - `step3c_search_sz.json`
  - `step3d_search_ks.json`
  - `step4_plan.json`
  - `step4b_ordered_cells.json`
  - `step5_mission_trace.json`
  - `final_result.json`
- Ostatni katalog uruchomienia: `output/latest_run.txt`

## Uwagi

- Strategia wykonania jest celowo prosta i deterministyczna.
- Część LLM nie steruje krytyczną logiką kosztów AP, a jedynie wspiera priorytetyzację obszarów.
