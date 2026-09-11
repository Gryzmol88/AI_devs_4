# Lesson 5 - Sekwencja Dwóch Agentów (drone)

Projekt realizuje sekwencję:
1. `map_agent` (vision, OpenRouter) - znajduje sektor tamy na mapie.
2. `pilot_agent` (function calling, OpenRouter) - buduje instrukcje sterowania dronem i wysyła je do `/verify`, reagując na feedback.

## Modele

- Agent mapy: `google/gemini-3-flash-preview` (domyślnie)
- Agent pilota: `openai/gpt-4o` (domyślnie)

## Wymagania

- Uzupełniony `Season2/.env`:
  - `OPENROUTER_API_KEY`
  - `HUB_API_KEY`
- Zainstalowane zależności z głównego `requirements.txt`

## Uruchomienie sekwencji

```bash
python Season2/lesson5_dron/main.py
```

## Function-calling pilota

Do agenta pilota przekazywane są wyłącznie podstawowe funkcje sterowania:
- `setDestinationObject`
- `setSector`
- `setDestroy`
- `setAltitude`
- `flyToLocation`
- `hardReset`
- `finishPlan` (zamknięcie budowy planu)

## Struktura output

Każde uruchomienie tworzy:
- `output/sequence_<timestamp>/01_map/<timestamp>/...`
- `output/sequence_<timestamp>/02_pilot/<timestamp>/...`
- `output/sequence_<timestamp>/sequence_result.json`
- `output/sequence_<timestamp>/sequence_summary.txt`

W środku etapów są m.in.:
- `config.json`
- `run_trace.jsonl`
- request/response endpointów
- wyniki końcowe (`result.json`, `summary.txt`)

