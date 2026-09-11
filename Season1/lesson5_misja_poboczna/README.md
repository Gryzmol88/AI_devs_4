# lesson5_misja_poboczna

Starter do wskazowki: "Nie bede czekac 4 minuty!".

Idea:
- skrypt wykonuje kroki `railway`,
- nie blokuje terminala na dlugie okna rate-limit,
- zapisuje checkpoint i konczy proces,
- wznowienie to ponowne uruchomienie skryptu.

## Uruchomienie

Ustaw klucz API:
- `HUB_API_KEY`, albo
- `API_KEY`

Nastepnie:

```bash
python lesson5_misja_poboczna/main.py
```

Tryb agresywny (bez czekania na limity):

```bash
python lesson5_misja_poboczna/main.py --mode aggressive
```

W tym trybie skrypt:
- ignoruje `Retry-After`,
- wysyla szybkie kolejne zapytania,
- loguje kazda probe do `output/aggressive_log.jsonl`,
- zatrzymuje sie dopiero po znalezieniu flagi innej niz `{FLG:COUNTRYROADS}`
  albo po przekroczeniu limitu prob.

## Jak dziala "nie czekam 4 minuty"

- Przy `429` skrypt czyta naglowki (`Retry-After`, `X-RateLimit-*`, `RateLimit-*`).
- Jesli czas oczekiwania jest wiekszy niz `MAX_LOCAL_WAIT_SECONDS` (domyslnie 12 s),
  zapisuje stan do `output/state.json` i konczy.
- Kolejne uruchomienie kontynuuje od ostatniego kroku.

## Konfiguracja

W `.env` mozna ustawic:
- `MAX_LOCAL_WAIT_SECONDS`
- `REQUEST_TIMEOUT_SECONDS`
- `RETRIES_ON_503`
- `AGGRESSIVE_MAX_ATTEMPTS`
- `AGGRESSIVE_DELAY_SECONDS`
- `AGGRESSIVE_ACTION`
- `AGGRESSIVE_ROUTE`
