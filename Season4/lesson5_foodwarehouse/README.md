# lesson5_foodwarehouse

Rozwiązanie zadania `foodwarehouse` w architekturze deterministycznej z warstwą agentową OpenRouter do podpowiedzi SQL.

## Założenia

- Konfiguracja ładowana przez Pydantic z pliku `Season4/.env`.
- Wszystkie wywołania do zadania idą przez endpoint `/verify`.
- Mapa `city -> destination` i dane autora do podpisu są pobierane przez SQL z narzędzia `database`.
- Gdy zapytania SQL w `.env` są puste, aplikacja używa auto-discovery tabel `destinations` i `users`.
- Wyniki pośrednie i finalne są zapisywane do katalogu `output`.

## Struktura

- `main.py` - uruchomienie całego procesu.
- `config.py` - ustawienia Pydantic.
- `api_client.py` - klient API `/verify`.
- `openrouter_client.py` - klient OpenRouter.
- `services/warehouse_service.py` - główna orkiestracja.
- `services/db_discovery.py` - odczyt schematu i danych bazy.
- `services/signature_service.py` - generowanie podpisów.
- `models/schemas.py` - modele Pydantic.
- `utils/logger.py` - krótkie logi terminalowe.
- `utils/io.py` - zapis snapshotów do `output`.

## Wymagane zmienne `.env`

Skopiuj wartości z `.env.example` do `Season4/.env` i uzupełnij:

- `AIDEVS_API_KEY`
- `OPENROUTER_API_KEY`
- `CITY_DESTINATION_QUERY` (opcjonalnie)
- `CREATOR_QUERY` (opcjonalnie)
- `SIGNATURE_TEMPLATE_JSON`

### Ważne mapowania SQL

1. `CITY_DESTINATION_QUERY` jeśli ustawione, powinno zwracać pola:
   - `city`
   - `destination`
2. `CREATOR_QUERY` jeśli ustawione, powinno zwracać:
   - `id` (lub `creatorID` / `creator_id`)
   - dodatkowe pola używane przez `SIGNATURE_TEMPLATE_JSON`

## Przebieg działania

1. Pobranie `help`.
2. Pobranie `food4cities.json`.
3. Odczyt tabel przez `database`.
4. Odczyt i zapis schematu tabel.
5. Odczyt mapowania `city -> destination` i danych autora.
6. Generowanie podpisu.
7. Tworzenie zamówień `orders.create` (domyślnie jedno zbiorcze).
8. Uzupełnianie zamówień `orders.append` (batch).
9. Finalna walidacja `done`.

## Pliki wyjściowe

Przy każdym uruchomieniu tworzony jest folder:

- `output/YYYYMMDD_HHMMSS/`

W tym folderze powstają m.in.:

- `step1_help.json`
- `step2_food4cities_raw.json`
- `step3_city_demands_normalized.json`
- `step4_db_tables.json`
- `step5_destinations_rows.json`
- `step6_creators.json`
- `step7_order_plan.json`
- `step8_created_orders.json`
- `step9_done_response.json`
- `final_result.txt`
- `final_response.json`
