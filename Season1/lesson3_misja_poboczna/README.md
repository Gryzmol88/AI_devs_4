# lesson3_misja_poboczna

Kompletne rozwiazanie jest teraz w tym folderze (bez zaleznosci od `lesson3_proxy`).

## Co tu jest

- `main.py` - endpoint HTTP `POST /` (`sessionID`, `msg` -> `msg`)
- `agent.py` - petla model + tool calling
- `tools.py` - `check_package` i `redirect_package`
- `sessions.py` - pamiec sesji per `sessionID`
- `config.py` - ladowanie `.env` i konfiguracja OpenRouter
- `probe_sidequest_v2.ps1`, `probe_sidequest_v3.ps1` - skrypty probingowe
- `probe_sidequest_v4.ps1` - adaptacyjny probing anty-petla

## Model

Domyslnie ustawiony jest:

- `OPENROUTER_MODEL=anthropic/claude-sonnet-4.6 (w tym folderze i tak wymuszony kodem)`

## Konfiguracja

Korzystamy z jednego pliku:

- `AI_devs_4/.env` (katalog glowny projektu)

Ustaw tam minimum:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`
- `OPENROUTER_MODEL=anthropic/claude-sonnet-4.6 (w tym folderze i tak wymuszony kodem)`
- `HUB_API_KEY`

## Uruchomienie

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r lesson3_misja_poboczna\requirements.txt
uvicorn lesson3_misja_poboczna.main:app --host 0.0.0.0 --port 3001 --reload
```

## Szybki test lokalny

```powershell
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:3001/" -ContentType "application/json" -Body '{"sessionID":"t1","msg":"Jaka pogoda w Krakowie?"}'
```

## Probing misji pobocznej

```powershell
.\lesson3_misja_poboczna\probe_sidequest_v3.ps1 -Url "https://TWOJ-URL/" -SessionId "sidequest-weather-krk-003"
```

Uwaga: skrypt v3 akceptuje flage tylko wtedy, gdy odpowiedz jest samym kodem `{FLG:...}`.

## Reczne pytania z terminala

Mozesz rozmawiac recznie przez CLI:

```powershell
python Season1\lesson3_misja_poboczna\chat_cli.py --url "https://nontheoretic-unsublimed-aundrea.ngrok-free.dev/" --session-id "manual-001"
```

Koniec rozmowy: `/exit`
