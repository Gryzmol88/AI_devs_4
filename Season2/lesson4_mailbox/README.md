# Season2/lesson4_mailbox

Rozwiązanie zadania `mailbox` z S02E04 w trybie **agent + function calling** z użyciem **OpenRouter**.

## Cechy

- Konfiguracja oparta o **Pydantic** (`AppConfig`).
- LLM przez OpenRouter (`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `MAILBOX_MODEL`).
- Agentowa pętla narzędziowa (function calling):
  - `zmail_help`
  - `get_inbox`
  - `search_mails`
  - `get_messages`
  - `get_thread_messages`
  - `extract_candidates`
  - `verify_answer`
  - `finish`
- Zapis wszystkich pobranych i wyselekcjonowanych maili do `output`.
- Szczegółowe logi runtime + `run_trace.jsonl` + `llm_trace.jsonl`.

## Uruchomienie

```powershell
$env:MAILBOX_MAX_AGENT_STEPS="14"
.venv\Scripts\python.exe Season2/lesson4_mailbox/main.py --max-rounds 1 --poll-seconds 0
```

## Wyniki

Każde uruchomienie tworzy katalog:

`Season2/lesson4_mailbox/output/<YYYYMMDD_HHMMSS>/`

W środku m.in.:

- `config.json`
- `help.json` (jeśli dostępne)
- `run_trace.jsonl`
- `llm_trace.jsonl`
- `all_messages/*.json|*.md`
- `selected_messages/*.json|*.md`
- `result.json`
