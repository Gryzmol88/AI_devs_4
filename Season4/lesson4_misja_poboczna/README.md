# lesson4_misja_poboczna

Narzędzie do eksploracji API pod kątem sekretu misji pobocznej lekcji 4.

## Co robi

1. Wysyła serię bezpiecznych zapytań (`help`, `listFiles`).
2. Testuje ścieżki związane z `flag` także w wariancie ASCII (`70 76 65 71`).
3. Zapisuje pełny trace request/response do `output/<timestamp>/`.

Domyślnie uruchamia tryb `check_flag_ord`, który:

1. robi `reset`,
2. tworzy `/flag`,
3. tworzy cztery pliki o rozmiarach `70/76/65/71` (nazwy nie są istotne),
4. pobiera `listFiles /flag`,
5. zapisuje raport walidacji kolejności rozmiarów do `step3_flag_ord_validation.json`.

Tryb `check_flag_ord_with_main` robi to samo, ale dodatkowo odtwarza
strukturę głównej misji (`/miasta`, `/osoby`, `/towary`) przed wysłaniem `done`.

## Konfiguracja

W `Season4/.env` ustaw:

- `AIDEVS_API_KEY` (lub `AG3NTS_API_KEY`)
- opcjonalnie `LESSON4_SIDE_TASK` (domyślnie `filesystem`)
- opcjonalnie `AIDEVS_VERIFY_URL`
- opcjonalnie `LESSON4_SIDE_MODE` (`probe`, `check_flag_ord`, `check_flag_ord_with_main`)
- opcjonalnie `LESSON4_SIDE_SUBMIT_DONE` (`true/false`)

## Uruchomienie

```bash
python main.py
```

## Artefakty

W katalogu `output/<timestamp>/`:

- `step0_plan.json` - lista probe'ów
- `step1_probe_results.json` - wynik każdego kroku
- `step2_http_trace.json` - pełny ślad HTTP
- `step3_flag_ord_validation.json` - raport walidacji rozmiarów/kolejności (tylko w trybie `check_flag_ord`)
- `final_summary.json` - podsumowanie
