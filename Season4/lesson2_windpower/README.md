# lesson2_windpower

Implementacja zadania `windpower` dla AI Devs Season4.

## Cel

Program:
- pobiera opis akcji (`help`)
- uruchamia okno serwisowe (`start`)
- kolejkowuje raporty przez `get` i odbiera je przez `getResult`
- wylicza harmonogram ochrony i produkcji turbiny
- podpisuje kazdy punkt konfiguracji (`unlockCodeGenerator`)
- wysyla konfiguracje (`config`)
- wykonuje test turbiny (`turbinecheck`)
- finalizuje zadanie (`done`)

## Konfiguracja

1. Uzyj `Season4/.env` jako glownego pliku konfiguracyjnego.
2. Przyklad zmiennych znajdziesz w `.env.example`.
3. Konfiguracja jest ladowana przez `pydantic-settings` w `config.py`.

## Uruchomienie

```bash
python main.py
```

## Struktura

- `main.py` - punkt wejscia i skladanie zaleznosci
- `config.py` - konfiguracja aplikacji przez Pydantic
- `clients/` - klienci API (`verify`, OpenRouter)
- `services/` - orchestrator, planner, collector, signer
- `models/` - modele domenowe planowania
- `utils/` - logger i operacje IO
- `output/` - artefakty uruchomien (katalog per run)

## Artefakty w output

Kazde uruchomienie tworzy osobny katalog czasowy z plikami:
- `step1_help.json`
- `step2_selected_params.json`
- `step3_start.json`
- `step4_enqueued.json`
- `step5_reports_raw.json`
- `step5b_getresult_trace.json`
- `step6_plan.json`
- `step7_configs_signed.json`
- `step8_config_response.json`
- `step9_turbinecheck.json`
- `step9b_getresult_trace.json`
- `step10_done.json`
- `step11_timing.json`
- `final_result.txt`

## Uwagi implementacyjne

- Program nie zaklada sztywnego formatu raportow i probuje mapowac klucze po nazwach.
- W sciezce krytycznej nie korzysta z LLM. OpenRouter jest opcjonalny i sluzy tylko diagnostyce.
- Logi terminalowe sa krotkie i pokazuja postep etapow.
