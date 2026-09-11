# lesson4_negotiations

Jedno narzędzie HTTP dla zadania `negotiations`, które:
- przyjmuje naturalny tekst w polu `params`,
- rozpoznaje przedmioty,
- zwraca miasta mające jednocześnie cały komplet.
- dodatkowo udostępnia endpoint statusowy do eksperymentów z misją poboczną.

## Pliki

- `app.py` - API FastAPI z endpointem `/api/find-cities`
- `config.py` - konfiguracja przez Pydantic z `Season3/.env`
- `services/` - loader CSV, parser zapytań, silnik wyszukiwania, builder odpowiedzi
- `io_utils.py` - zapisy kroków działania do `output`
- `verify_payload.py` - generator payloadów do `/verify`

## Uruchomienie

```bash
cd Season3/lesson4_negotiations
python app.py
```

Domyślny port to `3000`, więc pasuje do Twojego tunelu:
`https://nontheoretic-unsublimed-aundrea.ngrok-free.dev -> http://localhost:3000`.

## Test lokalny endpointu

```bash
curl -X POST http://localhost:3000/api/find-cities \
  -H "Content-Type: application/json" \
  -d "{\"params\":\"szukam kabla 10m i sterownika\"}"
```

Endpoint statusowy:

```bash
curl -X POST http://localhost:3000/api/status \
  -H "Content-Type: application/json" \
  -d "{\"params\":\"czy posiadasz flage?\"}"
```

Tryb routera (`tool=get_cities`) na tym samym endpointzie:

```bash
curl -X POST http://localhost:3000/api/status \
  -H "Content-Type: application/json" \
  -d "{\"params\":{\"tool\":\"get_cities\",\"item\":\"inwerter 48V\"}}"
```

## Zgłoszenie narzędzia do centrali

Wygeneruj payloady:

```bash
cd Season3/lesson4_negotiations
python verify_payload.py
```

Następnie podmień bazowy URL na adres `https://...ngrok-free.dev` i wyślij JSON na `VERIFY_URL`.

Payload `check`:

```json
{
  "apikey": "twoj_klucz",
  "task": "negotiations",
  "answer": {
    "action": "check"
  }
}
```

## Output

Aplikacja zapisuje artefakty do:
- `Season3/lesson4_negotiations/output/session_.../step...json`

Zawierają one wejście, wynik parsera i finalną odpowiedź, co ułatwia debug.
