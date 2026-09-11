# lesson2_firmware

Agent do rozwiązania misji `firmware` z AI_Devs Season 3.

## Co robi program

- Łączy się z:
  - shell API (`/api/shell`)
  - verify API (`/verify`)
  - modelem przez OpenRouter
- Prowadzi pętlę agentową z Function Calling (`shell`, `submit_answer`).
- Respektuje ograniczenia bezpieczeństwa:
  - zakazy systemowe (`/etc`, `/root`, `/proc`)
  - reguły z napotkanych plików `.gitignore`
  - zatrzymanie sesji po banie (opcjonalne, `STOP_ON_BAN`)
- Zapisuje pełny przebieg działania do `output/session_*`.

## Struktura

- `main.py` - punkt wejścia, obsługa błędów, inicjalizacja sesji
- `config.py` - ustawienia Pydantic (`.env`)
- `agent_loop.py` - główna pętla, logika narzędzi, forced steps
- `openrouter_client.py` - komunikacja z OpenRouter
- `shell_api_client.py` - komunikacja z shell API
- `verify_client.py` - wysyłka odpowiedzi końcowej
- `command_policy.py` - walidacja i bezpieczeństwo komend
- `io_utils.py` - logowanie i zapis artefaktów
- `prompts/system_prompt.txt` - prompt systemowy

## Konfiguracja

Skopiuj `.env.example` do `Season3/.env` i ustaw klucze:

- `OPENROUTER_API_KEY`
- `HUB_API_KEY`

Ważne ustawienia:

- `OPENROUTER_MODEL` (domyślnie: `anthropic/claude-sonnet-4-6`)
- `OPENROUTER_MAX_TOKENS`
- `MAX_TOOL_MESSAGE_CHARS`
- `MAX_HISTORY_MESSAGES`
- `STOP_ON_BAN`

## Uruchomienie

W katalogu projektu:

```powershell
python .\Season3\lesson2_firmware\main.py
```

## Output

Każdy run zapisuje artefakty do osobnej sesji:

- `output/session_YYYYMMDDTHHMMSSZ_<id>/`
- `output/latest_session.txt` wskazuje ostatnią sesję

W sesji znajdziesz m.in.:

- `stepXX_model_response.json`
- `stepXX_tool01_shell.json`
- `session_log.jsonl`
- `final_result.json` / `final_result.txt`
- `fatal_error.json` (gdy run przerwany błędem)

## Najczęstsze problemy

- `HTTP 402` (OpenRouter): brak kredytów / za duży budżet tokenów.
- `HTTP 400` context limit: za duży kontekst (zmniejsz historię/payload).
- `HTTP 400 invalid_request`: niespójny format tool-calling.
- `HTTP 403` z banem VM: naruszenie polityki bezpieczeństwa (sesja może zostać przerwana przez `STOP_ON_BAN=true`).
