# lesson5_misja_poboczna

Propozycja rozwiązania sidequesta na podstawie wskazówki:

`Fuksja widziała balon w Radomiu`

## Hipoteza robocza

Najbardziej prawdopodobny trop to:
- obiekt: `balon`
- lokalizacja: `Radom`
- słowo kluczowe sidequesta może być jednym z wariantów:
  - `RADOM`
  - `balon`
  - `BALON_RADOM`
  - `fuksja`
  - `FUKSJA`

## Strategia rozwiązania

1. Traktuj hint jako dane semantyczne:
- `Fuksja` może być:
  - nazwą obserwatora/kryptonimu,
  - nazwą koloru (fuchsia),
  - nazwą obiektu (np. dron/agent).

2. Zbuduj listę kandydatów odpowiedzi:
- format prosty: pojedyncze słowo (`RADOM`, `balon`, `fuksja`),
- format złożony: para (`balon`, `Radom`) lub string łączony (`BALON_W_RADOMIU`),
- warianty wielkości liter i znaków diakrytycznych.

3. Wyślij kandydatów sekwencyjnie do `/verify`:
- loguj kod odpowiedzi i `message`,
- po każdym błędzie koryguj format na podstawie feedbacku API,
- zatrzymaj się, gdy pojawi się `{FLG:...}`.

4. Jeśli API sugeruje inny schemat `answer`:
- dopasuj pole wejściowe (`answer`, `answer.<field>`, tablica, obiekt),
- utrzymuj krótkie serie prób i zapis pełnego trace.

## Plan implementacyjny (minimalny)

1. Wejście:
- `HUB_API_KEY`, `VERIFY_URL`, `SIDE_TASK_NAME` z `.env`.

2. Dane:
- lista kandydatów generowana ze wskazówki.

3. Pętla:
- `POST /verify` dla kolejnych kandydatów,
- adaptacja formatu po komunikatach błędu.

4. Output:
- `output/submit_trace.jsonl` (każda próba),
- `output/result.json` (status, trafiony kandydat, flaga).

## Dlaczego ta strategia

Wskazówka jest krótka i prawdopodobnie celowo niejednoznaczna, więc
najszybsze podejście to iteracyjne zawężanie przez feedback `/verify`,
zamiast zgadywania jednego „idealnego” formatu odpowiedzi.

## Skan Radomia (kod gotowy)

Skrypt: `radom_sidequest_scan.py`

Co robi:
- ustawia cel na `PWR8406PL` (Radom),
- ustawia LED na fuksję `#FF00FF`,
- opcjonalnie dodaje cele `set(video)` i `set(image)`,
- skanuje sektory siatki `3x4`,
- zapisuje odpowiedzi `/verify` do `output/radom_sidequest_scan_<timestamp>/`.

Uruchomienie:

```powershell
.venv\Scripts\python.exe Season2\lesson5_misja_poboczna\radom_sidequest_scan.py
```

Output:
- `config.json`
- `scan_trace.jsonl`
- `sector_<col>_<row>.json`
- `result.json`
