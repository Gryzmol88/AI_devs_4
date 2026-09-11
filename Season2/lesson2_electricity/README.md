# lesson2_electricity

Agent AI do zadania `electricity` zgodny ze wskazówkami z lekcji:
- używa **Function Calling** (orchestrator + narzędzia),
- analizuje planszę przez modele vision,
- buduje plan deterministycznie na podstawie portów `U/R/D/L`,
- wykonuje obroty **partiami** i robi weryfikację po batchu.
- gdy odczyt portów jest niespójny, używa fallbacku vision do planu obrotów.

## Jak działa

1. `fetch_target_board` - odczyt planszy docelowej.
2. `fetch_current_board` - odczyt planszy bieżącej (opcjonalnie z resetem).
3. `build_rotation_plan` - porównanie current vs target i wyliczenie obrotów.
4. `execute_rotation_batch` - wykonanie partii ruchów (lub symulacja w dry-run).
5. `get_runtime_status` - kontrola postępu i decyzja o kolejnych krokach.

## Zmienne środowiskowe (czytane z `Season2/.env`)

Wymagane:
- `HUB_API_KEY` (lub `API_KEY`)
- `OPENROUTER_API_KEY`

Opcjonalne:
- `OPENROUTER_BASE_URL` (domyślnie `https://openrouter.ai/api/v1`)
- `ELECTRICITY_ORCHESTRATOR_MODEL` (domyślnie `openai/gpt-4.1-mini`)
- `ELECTRICITY_VISION_MODELS` (CSV modeli, domyślnie `google/gemini-3-flash-preview`)
- `VERIFY_URL` (domyślnie `https://hub.ag3nts.org/verify`)
- `ELECTRICITY_TASK_NAME` (domyślnie `electricity`)
- `ELECTRICITY_BOARD_URL_TEMPLATE` (domyślnie `https://hub.ag3nts.org/data/{apikey}/electricity.png`)
- `ELECTRICITY_SOLVED_URL` (domyślnie `https://hub.ag3nts.org/i/solved_electricity.png`)
- `REQUEST_TIMEOUT_SECONDS` (domyślnie `60`)
- `ELECTRICITY_MAX_ROUNDS` (domyślnie `16`)
- `ELECTRICITY_MAX_ROTATIONS` (domyślnie `120`)
- `ELECTRICITY_BATCH_SIZE` (domyślnie `4`)
- `ELECTRICITY_ALLOW_VISION_FALLBACK` (domyślnie `false`, włącza agresywny fallback planowania)

## Uruchomienie

Tryb bezpieczny (domyślny, bez wysyłania obrotów):

```powershell
python Season2\lesson2_electricity\main.py --reset-first
```

Tryb wykonania (realne obroty do API):

```powershell
python Season2\lesson2_electricity\main.py --execute --reset-first
```

Nadpisanie limitu obrotów:

```powershell
python Season2\lesson2_electricity\main.py --execute --max-steps 80
```

## Artefakty wyjściowe (`output/`)

- `run_meta.json` - parametry uruchomienia,
- `llm_trace.jsonl` - decyzje orchestratora (Function Calling),
- `tool_trace.jsonl` - wyniki lokalnych narzędzi,
- `verify_trace.jsonl` - request/response do `/verify` (tylko przy `--execute`),
- `boards/*.png` - wizualne snapshoty planszy (`latest_current.png`, `latest_target.png`),
- `result.json` - raport końcowy.

### Test odczytu vision (bez obrotów)

Możesz uruchomić sam test oznaczania kafli:

```powershell
python Season2\lesson2_electricity\main.py --inspect-vision --reset-first
```

Program:
- pobiera aktualny i wzorcowy PNG,
- parsuje oba obrazy modelem vision,
- wypisuje adnotacje w formacie `AxB ["U","R",...]`,
- kończy działanie bez wysyłania `rotate`.
