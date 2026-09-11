# lesson1_kontekst

Automat do zadania `categorize`:
- pobiera swiezy CSV przed kazda proba,
- wysyla 10 zapytan `POST /verify` (jedno na towar),
- iteracyjnie poprawia prompt na podstawie feedbacku z huba,
- probuje resetu miedzy podejsciami,
- konczy po znalezieniu `{FLG:...}`.

## Wymagane zmienne (`.env` / `Season2/.env`)

- `HUB_API_KEY` (lub `API_KEY`)
- `CATEGORIZE_CSV_URL` (alternatywnie `ITEMS_CSV_URL`)
- `OPENROUTER_API_KEY` (dla automatycznego poprawiania promptu)

Opcjonalnie:
- `OPENROUTER_BASE_URL` (domyslnie `https://openrouter.ai/api/v1`)
- `PROMPT_ENGINEER_MODEL` (domyslnie `anthropic/claude-sonnet-4.6`)
- `MAX_PROMPT_ATTEMPTS` (domyslnie `12`)
- `REQUEST_TIMEOUT_SECONDS` (domyslnie `30`)
- `MAX_PROMPT_TOKENS` (domyslnie `100`)
- `ENABLE_CATEGORIZE_RESET` (`true`/`false`, domyslnie `true`)
- `CATEGORIZE_RESET_URL` (jesli znasz dedykowany endpoint resetu)
- `CATEGORIZE_PROMPT_TEMPLATE` (wlasny prompt startowy)

Domyslny szablon zawiera marker sesji pobocznej:
- `L:{label}` gdzie `label` jest kolejnymi literami `A..J` dla 10 zapytan.

Ten marker jest dodawany w promptach `VERIFY_ITEM_*` i moze byc potem odczytany
przez `Season2/lesson1_misja_poboczna`.

Jesli nie ustawisz `CATEGORIZE_CSV_URL`, skrypt automatycznie uzyje:
- `https://hub.ag3nts.org/data/{HUB_API_KEY}/categorize.csv`

Reset miedzy iteracjami jest wykonywany zgodnie z trescia zadania przez:
- `POST /verify` z `answer.prompt = \"reset\"`.

## Uruchomienie

```powershell
python Season2\lesson1_kontekst\main.py
```

## Wyniki

Zapisywane do:
- `Season2/lesson1_kontekst/output/cycle_log.jsonl`
- `Season2/lesson1_kontekst/output/api_trace.jsonl` (kazde zapytanie API + odpowiedz/error)
- `Season2/lesson1_kontekst/output/model_responses.jsonl` (odpowiedzi modelu prompt-engineera)
- `Season2/lesson1_kontekst/output/current_prompt.json`
- `Season2/lesson1_kontekst/output/result.json`
