# lesson1_misja_poboczna

Skrypt analizuje podpowiedź:

`Wysłałem 9132-1522-2306-1048-2119 hmmm... awkward :/`

i liczy wynik działania:

`9132 - 1522 - 2306 - 1048 - 2119 = 2137`

Następnie buduje kandydatów w formacie `answer.recheck`:

- `{"recheck": ["9132","1522","2306","1048","2119"]}`
- `{"recheck": [9132,1522,2306,1048,2119]}`
- `{"recheck": ["9132.json","1522.json","2306.json","1048.json","2119.json"]}`

## Uruchomienie

```powershell
cd M:\Michal\Programowanie\PYTHON\AI_devs_4\Season3\lesson1_misja_poboczna
python main.py
```

## Wysyłka kandydatów do /verify

```powershell
python main.py --verify
```

## Etap decode.txt

Pobranie i analiza decode.txt:

```powershell
python main.py --decode
```

Pobranie, analiza i wysyłka kandydatów `recheck` do `/verify`:

```powershell
python main.py --decode --verify
```

## Artefakty

- `output/step1_analysis.json`
- `output/final_result.txt`
- `output/verify_responses.json` (po `--verify`)
- `output/decode_raw.txt` (po `--decode`)
- `output/decode_candidates.json` (po `--decode`)
- `output/decode_recheck_candidates.json` (po `--decode`)
- `output/decode_verify_responses.json` (po `--decode --verify`)
- `output/decode_flag.txt` (po `--decode`, jeśli wykryto scenariusz AWK)

## Zmienne .env (plik `Season3/.env`)

- `HUB_API_KEY`
- `VERIFY_URL`
- `SIDE_TASK_NAME` (opcjonalnie, domyślnie `evaluation`)
- `SIDE_HINT_EXPRESSION` (opcjonalnie)
- `SIDE_DECODE_URL` (opcjonalnie, domyślnie `https://hub.ag3nts.org/dane/decode.txt`)
- `REQUEST_TIMEOUT_SECONDS` (opcjonalnie, domyślnie `30`)
