# lesson4_misja_poboczna

Eksplorator misji pobocznej dla S03E04 oparty o:
- skan `output` z misji głównej (`lesson4_negotiations/output`),
- skan danych wejściowych (`cities.csv`, `items.csv`, `connections.csv`),
- iteracyjne próby payloadów do `/verify` pod trop "cenzura",
- automatyczny polling `action=check` po każdym zgłoszeniu `tools`.

## Uruchomienie

```bash
cd Season3/lesson4_misja_poboczna
python main.py
```

## Co zapisuje

W `output/session_...`:
- `step1_main_output_scan.json` - analiza artefaktów misji głównej,
- `step2_input_data_scan.json` - analiza danych wejściowych,
- `step3_payload_candidates.json` - lista payloadów testowych,
- `step4_attempt_*.json` - odpowiedzi centrali dla kolejnych prób,
- `final_result.json` i `final_result.txt` - podsumowanie i ewentualna flaga.

## Uwaga

Skrypt domyślnie wykonuje aktywne próby `/verify` (`LESSON4_SIDE_ENABLE_VERIFY_EXPLORATION=true`).
Jeśli chcesz wyłączyć wysyłkę i zrobić tylko analizę danych, ustaw:

```env
LESSON4_SIDE_ENABLE_VERIFY_EXPLORATION=false
```

Do testów wariantów z `tools` ustaw URL aktywnego endpointu:

```env
LESSON4_SIDE_TOOL_URL=https://twoj-ngrok.ngrok-free.app/api/find-cities
```

## Ręczna zmiana opisu toola

Edytuj plik:

`manual_tool_description.txt`

Skrypt użyje tej treści jako pierwszego wariantu `tools[0].description`.
Nazwę pliku możesz zmienić przez:

```env
LESSON4_SIDE_MANUAL_DESCRIPTION_FILE=manual_tool_description.txt
```
