# Sendit Function Calling Tools

Modul `sendit_fc` dodaje agenta opartego o Function Calling z 4 narzedziami:

- `fetch_docs_recursive`
- `extract_nontext`
- `build_declaration_from_rules`
- `verify_sendit`

Konfiguracja jest ladowana przez `pydantic-settings` (klasa `SenditSettings`).

## Uruchomienie

Z katalogu repo:

```powershell
python -m lesson4_media.sendit_docs.sendit_fc.main
```

Opcjonalne parametry:

```powershell
python -m lesson4_media.sendit_docs.sendit_fc.main `
  --workspace-dir lesson4_media/sendit_docs `
  --model openai/gpt-5-mini `
  --max-iterations 12
```

## Wymagane zmienne srodowiskowe

- `OPENROUTER_API_KEY`
- `HUB_API_KEY`

Opcjonalnie:

- `OPENROUTER_BASE_URL` (domyslnie `https://openrouter.ai/api/v1`)
- `OPENROUTER_MODEL`
- `VISION_MODEL`

Uwaga:
- Ustawienia moga byc pobrane z env oraz z pliku `.env` przez `pydantic-settings`.

## Artefakty

- manifest: `lesson4_media/sendit_docs/manifest.csv`
- OCR: `lesson4_media/sendit_docs/parsed/nontext/*.md`
- deklaracja: `lesson4_media/sendit_docs/parsed/declaration.txt`
- verify response: `lesson4_media/sendit_docs/parsed/verify_response.json`
- trace function-calling: `lesson4_media/sendit_docs/parsed/fc_trace.json`
