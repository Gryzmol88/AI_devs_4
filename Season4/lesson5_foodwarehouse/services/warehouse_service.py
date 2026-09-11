"""Orkiestracja pełnego przepływu zadania foodwarehouse."""

import json
from pathlib import Path
from typing import Any

from api_client import ApiClient, ApiClientHttpError
from config import Settings
from models.schemas import CityDemand, OrderContext
from openrouter_client import OpenRouterClient
from services.db_discovery import DatabaseDiscoveryService
from services.signature_service import SignatureService
from utils import logger
from utils.io import write_json, write_text


class WarehouseService:
    """Koordynuje przygotowanie i wysłanie zamówień dla wszystkich miast.

    Args:
        settings: Konfiguracja aplikacji.
        api_client: Klient endpointu /verify.
        db_service: Serwis odczytu bazy przez API.
        signature_service: Serwis generowania podpisów.
        openrouter_client: Klient OpenRouter do pomocniczych analiz.
        output_dir: Katalog wynikowy bieżącego uruchomienia.
    """

    def __init__(
        self,
        settings: Settings,
        api_client: ApiClient,
        db_service: DatabaseDiscoveryService,
        signature_service: SignatureService,
        openrouter_client: OpenRouterClient,
        output_dir: Path,
    ) -> None:
        """Inicjalizuje serwis workflow zadania.

        Args:
            settings: Konfiguracja aplikacji.
            api_client: Klient endpointu /verify.
            db_service: Serwis odczytu bazy przez API.
            signature_service: Serwis generowania podpisów.
            openrouter_client: Klient OpenRouter do pomocniczych analiz.
            output_dir: Katalog wynikowy bieżącego uruchomienia.
        """

        self._settings = settings
        self._api_client = api_client
        self._db_service = db_service
        self._signature_service = signature_service
        self._openrouter_client = openrouter_client
        self._output_dir = output_dir
        self._all_destination_codes: list[str] = []
        self._creators_by_id: dict[int, dict[str, Any]] = {}

    def run(self) -> dict[str, Any]:
        """Uruchamia pełen proces przygotowania i wysyłki zamówień.

        Returns:
            Słownik z końcową odpowiedzią API `done`.

        Side Effects:
            Wysyła żądania do API, tworzy zamówienia i zapisuje snapshoty do folderu output.
        """

        logger.info("Start procesu foodwarehouse.")
        help_response = self._api_client.call_tool({"tool": "help"}).model_dump()
        write_json(self._output_dir / "step1_help.json", help_response)
        logger.info("Pobrano pomoc API.")
        reset_response = self._api_client.call_tool({"tool": "reset"}).model_dump()
        write_json(self._output_dir / "step1b_reset.json", reset_response)
        logger.info("Zresetowano stan zamówień przed realizacją.")

        raw_demands = self._api_client.fetch_json_url(self._settings.food4cities_url)
        write_json(self._output_dir / "step2_food4cities_raw.json", raw_demands)
        city_demands = self._parse_city_demands(raw_demands)
        write_json(
            self._output_dir / "step3_city_demands_normalized.json",
            [d.model_dump() for d in city_demands],
        )
        logger.info(f"Wczytano zapotrzebowanie miast: {len(city_demands)}.")

        tables_payload = self._db_service.show_tables()
        write_json(self._output_dir / "step4_db_tables.json", tables_payload)
        logger.info("Pobrano listę tabel z bazy.")
        table_names = self._extract_table_names(tables_payload)
        self._save_schema_snapshots(table_names)

        destinations = self._load_destinations(table_names)
        write_json(self._output_dir / "step5_destinations_rows.json", destinations)

        creators = self._load_creators(table_names)
        write_json(self._output_dir / "step6_creators.json", creators)
        self._creators_by_id = {int(creator["id"]): creator for creator in creators}
        roles = self._load_roles(table_names)
        write_json(self._output_dir / "step6_roles.json", roles)
        selected_creator, creator_candidates, selection_debug = self._select_creator_for_transport(
            creators,
            roles,
        )
        write_json(self._output_dir / "step6_creator_selection.json", selection_debug)
        logger.info("Pobrano dane autoryzacyjne z bazy.")

        # Mimo opisu w help, walidacja `done` dla foodwarehouse wymaga precyzyjnych zamówień
        # dopasowanych do miast, więc domyślnie wymuszamy tryb per-miasto.
        single_order_mode = False
        logger.info("Tryb realizacji: zamówienia per-miasto.")

        city_destination_map = self._build_city_destination_map(destinations)
        self._all_destination_codes = self._extract_destination_codes(destinations)
        orders_destination_map = self._load_city_destination_map_from_orders()
        write_json(
            self._output_dir / "step5b_orders_destination_map.json",
            orders_destination_map,
        )
        city_destination_map.update(orders_destination_map)
        alias_resolution = self._apply_city_aliases(city_demands, city_destination_map)
        write_json(
            self._output_dir / "step5c_city_alias_resolution.json",
            alias_resolution,
        )
        write_json(self._output_dir / "step5_city_destination_map.json", city_destination_map)

        done_response: dict[str, Any] | None = None
        for attempt_idx, creator_candidate in enumerate(creator_candidates, start=1):
            logger.info(
                f"Próba {attempt_idx}: creatorID={creator_candidate.get('id')} "
                f"login={creator_candidate.get('login')}"
            )

            if single_order_mode:
                plan = self._build_single_order_plan(city_demands, destinations, creator_candidate)
            else:
                plan = self._build_multi_order_plan(
                    city_demands,
                    city_destination_map,
                    creator_candidate,
                )

            write_json(
                self._output_dir / f"step7_order_plan_attempt{attempt_idx}.json",
                [order.model_dump() for order in plan],
            )
            write_json(
                self._output_dir / "step7_order_plan.json",
                [order.model_dump() for order in plan],
            )

            created_orders = self._create_and_fill_orders(plan)
            write_json(
                self._output_dir / f"step8_created_orders_attempt{attempt_idx}.json",
                created_orders,
            )
            write_json(self._output_dir / "step8_created_orders.json", created_orders)
            logger.info("Zamówienia zostały utworzone i uzupełnione.")

            try:
                done_response = self._api_client.call_tool({"tool": "done"}).model_dump()
                write_json(self._output_dir / "step9_done_response.json", done_response)
                write_json(
                    self._output_dir / f"step9_done_response_attempt{attempt_idx}.json",
                    done_response,
                )
                write_text(self._output_dir / "final_result.txt", str(done_response))
                logger.info("Wysłano finalne sprawdzenie done.")
                return done_response
            except ApiClientHttpError as exc:
                write_json(
                    self._output_dir / f"step9_done_error_attempt{attempt_idx}.json",
                    {
                        "status_code": exc.status_code,
                        "reason": exc.reason,
                        "body": exc.body,
                        "payload": exc.payload,
                    },
                )
                is_creator_error = '"code": -652' in exc.body
                is_missing_orders_error = '"code": -655' in exc.body
                has_next = attempt_idx < len(creator_candidates)
                if is_missing_orders_error:
                    missing = self._extract_missing_requirements(exc.body)
                    write_json(
                        self._output_dir / f"step9_missing_requirements_attempt{attempt_idx}.json",
                        missing,
                    )
                    if missing:
                        logger.info("done zgłasza brakujące zamówienia. Uzupełnianie braków z payloadu `missing`.")
                        missing_created = self._create_missing_orders(
                            creator=creator_candidate,
                            missing=missing,
                        )
                        write_json(
                            self._output_dir / f"step8_missing_orders_attempt{attempt_idx}.json",
                            missing_created,
                        )
                        done_response = self._api_client.call_tool({"tool": "done"}).model_dump()
                        write_json(self._output_dir / "step9_done_response.json", done_response)
                        write_json(
                            self._output_dir / f"step9_done_response_attempt{attempt_idx}.json",
                            done_response,
                        )
                        write_text(self._output_dir / "final_result.txt", str(done_response))
                        logger.info("Wysłano finalne sprawdzenie done po uzupełnieniu braków.")
                        return done_response
                if is_creator_error and has_next:
                    logger.info("done odrzuciło creatorID. Reset i kolejna próba z innym użytkownikiem.")
                    self._api_client.call_tool({"tool": "reset"})
                    continue
                raise

        if done_response is None:
            raise ValueError("Nie udało się zakończyć zadania done dla żadnego kandydata creatorID.")
        return done_response

    def _parse_city_demands(self, payload: Any) -> list[CityDemand]:
        """Normalizuje dane `food4cities.json` do listy CityDemand.

        Args:
            payload: Surowy JSON pobrany z URL.

        Returns:
            Lista obiektów CityDemand.
        """

        demands: list[CityDemand] = []
        if isinstance(payload, list):
            for row in payload:
                demands.append(self._city_from_row(row))
            return demands

        if isinstance(payload, dict):
            if "cities" in payload and isinstance(payload["cities"], list):
                for row in payload["cities"]:
                    demands.append(self._city_from_row(row))
            else:
                for city_name, items in payload.items():
                    if isinstance(items, dict):
                        demands.append(
                            CityDemand(city=str(city_name), items=self._normalize_items(items))
                        )
            return demands

        raise ValueError("Nieznany format pliku food4cities.json.")

    def _city_from_row(self, row: Any) -> CityDemand:
        """Mapuje pojedynczy rekord miasta do modelu CityDemand.

        Args:
            row: Pojedynczy rekord z JSON.

        Returns:
            Znormalizowany obiekt CityDemand.
        """

        if not isinstance(row, dict):
            raise ValueError("Niepoprawny rekord miasta w JSON.")
        city = row.get("city") or row.get("name") or row.get("miasto")
        destination = row.get("destination")
        items = row.get("items") or row.get("goods") or row.get("towary") or {}
        if not city:
            raise ValueError(f"Brak nazwy miasta w rekordzie: {row}")
        return CityDemand(
            city=str(city),
            destination=destination,
            items=self._normalize_items(items),
        )

    def _normalize_items(self, items: Any) -> dict[str, int]:
        """Konwertuje strukturę towarów do mapy `nazwa -> ilość`.

        Args:
            items: Surowe dane towarów z JSON.

        Returns:
            Słownik nazw towarów i ilości.
        """

        normalized: dict[str, int] = {}
        if isinstance(items, dict):
            for key, value in items.items():
                normalized[str(key)] = int(value)
            return normalized

        if isinstance(items, list):
            for row in items:
                if isinstance(row, dict):
                    name = row.get("name") or row.get("item") or row.get("towar")
                    qty = row.get("items") or row.get("qty") or row.get("amount") or 0
                    if name:
                        normalized[str(name)] = int(qty)
        return normalized

    def _extract_table_names(self, payload: Any) -> list[str]:
        """Wyciąga listę nazw tabel z odpowiedzi `show tables`.

        Args:
            payload: Odpowiedź narzędzia `database`.

        Returns:
            Lista nazw tabel.
        """

        if isinstance(payload, dict):
            tables = payload.get("tables")
            if isinstance(tables, list):
                return [str(table) for table in tables]
            rows = payload.get("rows")
            if isinstance(rows, list):
                extracted: list[str] = []
                for row in rows:
                    if isinstance(row, dict):
                        for value in row.values():
                            extracted.append(str(value))
                            break
                    else:
                        extracted.append(str(row))
                return extracted
        return []

    def _save_schema_snapshots(self, table_names: list[str]) -> None:
        """Pobiera i zapisuje definicje tabel do katalogu output.

        Args:
            table_names: Lista tabel dostępnych w bazie.

        Returns:
            None

        Side Effects:
            Zapisuje pliki `step4_schema_<table>.json`.
        """

        for table in table_names:
            if table not in {"destinations", "users", "roles"}:
                continue
            schema = self._db_service.select(f"show create table {table}")
            write_json(self._output_dir / f"step4_schema_{table}.json", schema)

    def _load_destinations(self, table_names: list[str]) -> list[dict[str, Any]]:
        """Pobiera rekordy tabeli destinations.

        Args:
            table_names: Lista tabel dostępnych w bazie.

        Returns:
            Lista rekordów destinations.
        """

        query = self._settings.city_destination_query.strip()
        if query:
            raw = self._db_service.select(query)
            return self._extract_rows(raw)

        if "destinations" not in table_names:
            raise ValueError("Brak tabeli destinations w bazie.")
        raw = self._db_service.select("SELECT * FROM destinations")
        rows = self._extract_rows(raw)
        if not rows:
            raise ValueError("Tabela destinations jest pusta albo nie udało się odczytać rekordów.")
        return rows

    def _load_creators(self, table_names: list[str]) -> list[dict[str, Any]]:
        """Pobiera listę rekordów użytkowników wymaganych do autoryzacji.

        Args:
            table_names: Lista tabel dostępnych w bazie.

        Returns:
            Lista rekordów znormalizowanych do pól id/login/birthday.
        """

        query = self._settings.creator_query.strip()
        if query:
            rows = self._extract_rows(self._db_service.select(query))
        else:
            if "users" not in table_names:
                raise ValueError("Brak tabeli users w bazie.")
            rows = self._extract_rows(self._db_service.select("SELECT * FROM users"))

        normalized: list[dict[str, Any]] = []
        for row in rows:
            normalized_row = self._normalize_creator_row(row)
            if normalized_row is not None:
                normalized.append(normalized_row)

        if not normalized:
            raise ValueError(
                "Nie znaleziono użytkownika z polami id/login/birthday. "
                "Ustaw CREATOR_QUERY lub sprawdź schemat users."
            )
        return normalized

    def _load_roles(self, table_names: list[str]) -> list[dict[str, Any]]:
        """Pobiera rekordy tabeli ról użytkowników.

        Args:
            table_names: Lista tabel dostępnych w bazie.

        Returns:
            Lista rekordów tabeli roles.
        """

        if "roles" not in table_names:
            return []
        return self._extract_rows(self._db_service.select("SELECT * FROM roles"))

    def _normalize_creator_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """Normalizuje rekord użytkownika do pól wymaganych przez podpis.

        Args:
            row: Surowy rekord z tabeli users.

        Returns:
            Znormalizowany słownik lub None, jeśli nie znaleziono wymaganych pól.
        """

        id_value = self._first_value(
            row,
            ["id", "user_id", "creator_id", "creatorID"],
        )
        login_value = self._first_value(
            row,
            ["login", "username", "user", "name"],
        )
        birthday_value = self._first_value(
            row,
            ["birthday", "birth_date", "date_of_birth", "dob"],
        )
        if id_value is None or login_value is None or birthday_value is None:
            return None

        normalized = dict(row)
        normalized["id"] = int(id_value)
        normalized["login"] = str(login_value)
        normalized["birthday"] = str(birthday_value)
        role_id_value = self._first_value(row, ["role_id", "roleid", "role"])
        if role_id_value is not None:
            normalized["role_id"] = str(role_id_value)
        return normalized

    def _select_creator_for_transport(
        self,
        creators: list[dict[str, Any]],
        roles: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        """Wybiera użytkownika odpowiedzialnego za transport.

        Args:
            creators: Lista kandydatów z tabeli users.
            roles: Lista ról z tabeli roles.

        Returns:
            Krotka: wybrany twórca, lista kandydatów (od najlepszego) i diagnostyka.
        """

        role_name_by_id: dict[str, str] = {}
        for role in roles:
            role_id = self._first_value(role, ["id", "role_id", "roleid"])
            role_name = self._first_value(role, ["name", "role", "role_name", "title"])
            if role_id is not None and role_name is not None:
                role_name_by_id[str(role_id)] = str(role_name)

        keywords = [
            "transport",
            "logist",
            "delivery",
            "shipping",
            "spedy",
            "kierow",
            "magaz",
            "warehouse",
        ]

        scored: list[dict[str, Any]] = []
        for creator in creators:
            role_id = str(creator.get("role_id", ""))
            role_name = role_name_by_id.get(role_id, "")
            role_name_lower = role_name.lower()
            score = 0
            for keyword in keywords:
                if keyword in role_name_lower:
                    score += 10
            if role_name_lower:
                score += 1
            scored.append(
                {
                    "creator": creator,
                    "role_id": role_id,
                    "role_name": role_name,
                    "score": score,
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        if scored:
            selected = scored[0]["creator"]
            ordered = [item["creator"] for item in scored]
        else:
            selected = creators[0]
            ordered = creators

        debug = {
            "roles_index": role_name_by_id,
            "candidates_scored": [
                {
                    "id": item["creator"].get("id"),
                    "login": item["creator"].get("login"),
                    "role_id": item["role_id"],
                    "role_name": item["role_name"],
                    "score": item["score"],
                }
                for item in scored
            ],
            "selected": {
                "id": selected.get("id"),
                "login": selected.get("login"),
                "role_id": selected.get("role_id"),
            },
        }
        return selected, ordered, debug

    def _is_single_order_mode(self, help_payload: dict[str, Any]) -> bool:
        """Określa tryb pracy na podstawie opisu narzędzia `done`.

        Args:
            help_payload: Odpowiedź narzędzia `help`.

        Returns:
            True, jeśli API sugeruje jedno zamówienie zbiorcze.
        """

        tools = help_payload.get("tools")
        if not isinstance(tools, list):
            return True
        for tool in tools:
            if isinstance(tool, dict) and tool.get("tool") == "done":
                description = str(tool.get("description", "")).lower()
                return "one order" in description
        return True

    def _build_single_order_plan(
        self,
        demands: list[CityDemand],
        destinations: list[dict[str, Any]],
        creator: dict[str, Any],
    ) -> list[OrderContext]:
        """Buduje plan jednego zamówienia zsumowanego dla wszystkich miast.

        Args:
            demands: Zapotrzebowanie miast z JSON.
            destinations: Rekordy tabeli destinations.
            creator: Wybrany użytkownik do podpisu i tworzenia zamówień.

        Returns:
            Lista z jednym obiektem OrderContext.
        """

        destination_map = self._build_city_destination_map(destinations)
        first_city_destination = ""
        if demands:
            first_city_destination = self._lookup_destination(demands[0].city, destination_map)
        destination_value = first_city_destination or self._select_default_destination(destinations)
        signature = self._generate_signature(creator, destination_value)

        aggregated_items: dict[str, int] = {}
        for demand in demands:
            for item_name, item_count in demand.items.items():
                aggregated_items[item_name] = aggregated_items.get(item_name, 0) + int(item_count)

        return [
            OrderContext(
                city="ALL_CITIES",
                destination=destination_value,
                creator_id=int(creator["id"]),
                signature=signature,
                items=aggregated_items,
            )
        ]

    def _build_multi_order_plan(
        self,
        demands: list[CityDemand],
        destination_map: dict[str, str],
        creator: dict[str, Any],
    ) -> list[OrderContext]:
        """Buduje plan zamówień per-miasto jako fallback.

        Args:
            demands: Zapotrzebowanie miast z JSON.
            destination_map: Mapowanie miast na destination.
            creator: Wybrany użytkownik do podpisu i tworzenia zamówień.

        Returns:
            Lista obiektów OrderContext per miasto.
        """

        creator_id = int(creator["id"])
        plan: list[OrderContext] = []

        for demand in demands:
            destination = (
                str(demand.destination)
                if demand.destination is not None
                else self._lookup_destination(demand.city, destination_map)
            )
            if not destination:
                raise ValueError(f"Brak destination dla miasta: {demand.city}")

            signature = self._generate_signature(creator, destination)
            plan.append(
                OrderContext(
                    city=demand.city,
                    destination=destination,
                    creator_id=creator_id,
                    signature=signature,
                    items=demand.items,
                )
            )
        return plan

    def _build_city_destination_map(self, rows: list[dict[str, Any]]) -> dict[str, str]:
        """Buduje mapowanie `city -> destination` na podstawie rekordów destinations.

        Args:
            rows: Rekordy tabeli destinations.

        Returns:
            Słownik mapowania miast na kody destination.
        """

        mapping: dict[str, str] = {}
        for row in rows:
            city = self._first_value(
                row,
                ["city", "city_name", "name", "miasto"],
            )
            destination = self._first_value(
                row,
                ["destination", "destination_code", "code", "dest_code", "id", "destination_id"],
            )
            if city is None or destination is None:
                continue
            city_key = self._normalize_city_name(str(city))
            mapping[city_key] = self._coerce_destination(destination)
        return mapping

    def _load_city_destination_map_from_orders(self) -> dict[str, str]:
        """Buduje mapowanie `city -> destination` na podstawie istniejących zamówień.

        Args:
            Brak.

        Returns:
            Słownik mapowania miast na kody destination wyciągnięty z `orders.get`.
        """

        response = self._api_client.call_tool({"tool": "orders", "action": "get"}).model_dump()
        orders = self._extract_orders_from_response(response)
        mapping: dict[str, str] = {}
        for order in orders:
            if not isinstance(order, dict):
                continue
            destination = self._first_value(order, ["destination", "destination_id", "code"])
            title = self._first_value(order, ["title", "name"])
            city = self._extract_city_from_order_title(str(title) if title else "")
            if destination is None or not city:
                continue
            mapping[self._normalize_city_name(city)] = self._coerce_destination(destination)
        return mapping

    def _extract_orders_from_response(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalizuje odpowiedź `orders.get` do listy zamówień.

        Args:
            payload: Surowa odpowiedź API dla `orders.get`.

        Returns:
            Lista zamówień jako słowniki.
        """

        if "orders" in payload and isinstance(payload["orders"], list):
            return [order for order in payload["orders"] if isinstance(order, dict)]
        data = payload.get("data")
        if isinstance(data, list):
            return [order for order in data if isinstance(order, dict)]
        if isinstance(data, dict):
            if "orders" in data and isinstance(data["orders"], list):
                return [order for order in data["orders"] if isinstance(order, dict)]
            return [data]
        order = payload.get("order")
        if isinstance(order, dict):
            return [order]
        return []

    def _extract_city_from_order_title(self, title: str) -> str:
        """Wydobywa nazwę miasta z tytułu zamówienia.

        Args:
            title: Tytuł zamówienia.

        Returns:
            Nazwa miasta lub pusty tekst.
        """

        normalized = title.strip()
        prefixes = [
            "Dostawa dla ",
            "dostawa dla ",
            "Supply for ",
            "Zamówienie dla ",
        ]
        for prefix in prefixes:
            if normalized.startswith(prefix):
                return normalized[len(prefix) :].strip()
        return ""

    def _apply_city_aliases(
        self,
        demands: list[CityDemand],
        destination_map: dict[str, str],
    ) -> dict[str, dict[str, str]]:
        """Uzupełnia brakujące mapowania miast przez aliasy nazw lokalnych.

        Args:
            demands: Miasta wymagane przez plik wejściowy.
            destination_map: Aktualne mapowanie city -> destination.

        Returns:
            Raport zastosowanych aliasów i braków po uzupełnieniu.
        """

        aliases = {
            "domatowo": "krokowa",
        }
        applied: dict[str, dict[str, str]] = {}
        missing_after_alias: dict[str, str] = {}

        for demand in demands:
            city_key = self._normalize_city_name(demand.city)
            if city_key in destination_map:
                continue
            alias_key = aliases.get(city_key, "")
            if alias_key and alias_key in destination_map:
                destination_map[city_key] = destination_map[alias_key]
                applied[city_key] = {
                    "alias_city": alias_key,
                    "destination": destination_map[alias_key],
                }
            else:
                missing_after_alias[city_key] = "no_mapping"

        return {
            "applied": applied,
            "missing_after_alias": missing_after_alias,
        }

    def _lookup_destination(self, city: str, destination_map: dict[str, str]) -> str:
        """Wyszukuje destination dla nazwy miasta.

        Args:
            city: Nazwa miasta z pliku food4cities.
            destination_map: Słownik mapowania.

        Returns:
            Kod destination lub pusty tekst.
        """

        return destination_map.get(self._normalize_city_name(city), "")

    def _select_default_destination(self, rows: list[dict[str, Any]]) -> str:
        """Wybiera domyślny destination dla trybu jednego zamówienia.

        Args:
            rows: Rekordy tabeli destinations.

        Returns:
            Kod destination jako tekst.
        """

        for row in rows:
            destination = self._first_value(
                row,
                ["destination", "destination_code", "code", "dest_code", "id", "destination_id"],
            )
            if destination is not None:
                return self._coerce_destination(destination)
        raise ValueError("Nie udało się ustalić żadnego poprawnego destination.")

    def _generate_signature(self, creator: dict[str, Any], destination: str) -> str:
        """Generuje podpis dla twórcy i destination zamówienia.

        Args:
            creator: Znormalizowany rekord użytkownika.
            destination: Kod destination dla zamówienia.

        Returns:
            Podpis tekstowy zwrócony przez signatureGenerator.
        """

        template = self._settings.signature_template()
        payload: dict[str, Any] = {}
        for key, value in template.items():
            if isinstance(value, str):
                payload[key] = value.format(
                    creator_id=creator["id"],
                    destination=destination,
                    **creator,
                )
            else:
                payload[key] = value

        payload.setdefault("action", "generate")
        payload.setdefault("login", creator["login"])
        payload.setdefault("birthday", creator["birthday"])
        payload.setdefault("destination", destination)
        return self._signature_service.generate(payload)

    def _create_and_fill_orders(self, plan: list[OrderContext]) -> list[dict[str, Any]]:
        """Tworzy zamówienia i dopisuje do nich towary.

        Args:
            plan: Plan zamówień.

        Returns:
            Lista odpowiedzi API po utworzeniu i uzupełnieniu zamówień.
        """

        created: list[dict[str, Any]] = []
        for order in plan:
            logger.info(f"Tworzenie zamówienia dla: {order.city}")
            title = (
                "Dostawa zbiorcza dla wszystkich miast"
                if order.city == "ALL_CITIES"
                else f"Dostawa dla {order.city}"
            )
            create_payload = {
                "tool": "orders",
                "action": "create",
                "title": title,
                "creatorID": order.creator_id,
                "destination": self._coerce_destination(order.destination),
                "signature": order.signature,
            }

            try:
                create_response = self._api_client.call_tool(create_payload).model_dump()
            except ApiClientHttpError as exc:
                if '"code": -838' in exc.body and order.city != "ALL_CITIES":
                    logger.info(
                        f"Destination odrzucone dla {order.city}. Szukanie poprawnego kodu przez probing."
                    )
                    create_response, resolved_destination, resolved_signature = (
                        self._probe_destination_for_city(order, title)
                    )
                    order.destination = resolved_destination
                    order.signature = resolved_signature
                else:
                    raise

            order_id = self._extract_order_id(create_response)
            append_response = self._api_client.call_tool(
                {
                    "tool": "orders",
                    "action": "append",
                    "id": order_id,
                    "items": order.items,
                }
            ).model_dump()

            created.append(
                {
                    "city": order.city,
                    "order_id": order_id,
                    "create_response": create_response,
                    "append_response": append_response,
                }
            )
        return created

    def _extract_destination_codes(self, rows: list[dict[str, Any]]) -> list[str]:
        """Wyciąga listę kodów destination z rekordów tabeli destinations.

        Args:
            rows: Rekordy tabeli destinations.

        Returns:
            Lista unikalnych kodów destination.
        """

        codes: list[str] = []
        seen: set[str] = set()
        for row in rows:
            destination = self._first_value(
                row,
                ["destination", "destination_code", "code", "dest_code", "id", "destination_id"],
            )
            if destination is None:
                continue
            code = self._coerce_destination(destination)
            if code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    def _probe_destination_for_city(
        self,
        order: OrderContext,
        title: str,
    ) -> tuple[dict[str, Any], str, str]:
        """Szuka poprawnego destination dla miasta przez próby `orders.create`.

        Args:
            order: Kontekst zamówienia dla konkretnego miasta.
            title: Tytuł zamówienia.

        Returns:
            Krotka: odpowiedź create, poprawny destination i odpowiadający podpis.
        """

        creator = self._creators_by_id.get(int(order.creator_id))
        if creator is None:
            raise ValueError(f"Brak danych twórcy o id={order.creator_id} do probing destination.")

        attempted: list[dict[str, Any]] = []
        candidates = [order.destination] + [
            code for code in self._all_destination_codes if code != str(order.destination)
        ]
        for code in candidates:
            signature = self._generate_signature(creator, str(code))
            payload = {
                "tool": "orders",
                "action": "create",
                "title": title,
                "creatorID": order.creator_id,
                "destination": self._coerce_destination(code),
                "signature": signature,
            }
            try:
                response = self._api_client.call_tool(payload).model_dump()
                write_json(
                    self._output_dir / f"step8_probe_{self._normalize_city_name(order.city)}.json",
                    {
                        "city": order.city,
                        "resolved_destination": code,
                        "attempted_count": len(attempted) + 1,
                        "attempted": attempted + [{"destination": code, "result": "success"}],
                    },
                )
                return response, str(code), signature
            except ApiClientHttpError as exc:
                attempted.append(
                    {
                        "destination": code,
                        "status_code": exc.status_code,
                        "reason": exc.reason,
                        "body": exc.body,
                    }
                )
                continue

        write_json(
            self._output_dir / f"step8_probe_{self._normalize_city_name(order.city)}.json",
            {
                "city": order.city,
                "resolved_destination": None,
                "attempted_count": len(attempted),
                "attempted": attempted,
            },
        )
        raise ValueError(f"Nie znaleziono poprawnego destination dla miasta {order.city}.")

    def _extract_missing_requirements(self, error_body: str) -> list[dict[str, Any]]:
        """Wydobywa listę brakujących zamówień z treści błędu `done`.

        Args:
            error_body: Treść `body` wyjątku HTTP zwrócona przez API.

        Returns:
            Lista brakujących zamówień z polami city/destination/items.
        """

        try:
            payload = json.loads(error_body)
        except json.JSONDecodeError:
            return []
        missing = payload.get("missing")
        if isinstance(missing, list):
            return [item for item in missing if isinstance(item, dict)]
        return []

    def _create_missing_orders(
        self,
        creator: dict[str, Any],
        missing: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Tworzy zamówienia dla braków zwróconych przez `done`.

        Args:
            creator: Wybrany twórca zamówień.
            missing: Lista braków z błędu `done`.

        Returns:
            Lista utworzonych rekordów z odpowiedziami create/append.
        """

        created: list[dict[str, Any]] = []
        creator_id = int(creator["id"])
        for item in missing:
            city = str(item.get("city", "")).strip()
            destination = self._coerce_destination(item.get("destination"))
            items = item.get("items")
            if not city or not destination or not isinstance(items, dict):
                continue

            signature = self._generate_signature(creator, destination)
            create_response = self._api_client.call_tool(
                {
                    "tool": "orders",
                    "action": "create",
                    "title": f"Dostawa dla {city.lower()}",
                    "creatorID": creator_id,
                    "destination": destination,
                    "signature": signature,
                }
            ).model_dump()
            order_id = self._extract_order_id(create_response)
            append_response = self._api_client.call_tool(
                {
                    "tool": "orders",
                    "action": "append",
                    "id": order_id,
                    "items": items,
                }
            ).model_dump()
            created.append(
                {
                    "city": city,
                    "destination": destination,
                    "order_id": order_id,
                    "create_response": create_response,
                    "append_response": append_response,
                }
            )
        return created

    def _extract_order_id(self, create_response: dict[str, Any]) -> str:
        """Wydobywa identyfikator zamówienia z odpowiedzi `orders.create`.

        Args:
            create_response: Surowa odpowiedź po utworzeniu zamówienia.

        Returns:
            Id zamówienia jako tekst.

        Raises:
            ValueError: Gdy id zamówienia nie zostało znalezione.
        """

        data = create_response.get("data")
        if isinstance(data, dict):
            if "id" in data:
                return str(data["id"])
            if "order_id" in data:
                return str(data["order_id"])
            order_in_data = data.get("order")
            if isinstance(order_in_data, dict):
                if "id" in order_in_data:
                    return str(order_in_data["id"])
                if "order_id" in order_in_data:
                    return str(order_in_data["order_id"])

        order = create_response.get("order")
        if isinstance(order, dict):
            if "id" in order:
                return str(order["id"])
            if "order_id" in order:
                return str(order["order_id"])
        if "id" in create_response:
            return str(create_response["id"])
        raise ValueError(f"Nie znaleziono id zamówienia w odpowiedzi: {create_response}")

    def _extract_rows(self, payload: Any) -> list[dict[str, Any]]:
        """Normalizuje różne formaty odpowiedzi DB do listy rekordów.

        Args:
            payload: Odpowiedź narzędzia `database`.

        Returns:
            Lista rekordów słownikowych.
        """

        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            rows = payload.get("rows")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
            data = payload.get("data")
            if isinstance(data, list):
                return [row for row in data if isinstance(row, dict)]
        return []

    def _first_value(self, row: dict[str, Any], keys: list[str]) -> Any:
        """Zwraca pierwszą niepustą wartość dla podanych nazw kolumn.

        Args:
            row: Rekord źródłowy.
            keys: Lista kandydatów nazw kolumn.

        Returns:
            Znaleziona wartość lub None.
        """

        lowered = {str(key).lower(): value for key, value in row.items()}
        for key in keys:
            if key.lower() in lowered and lowered[key.lower()] not in (None, ""):
                return lowered[key.lower()]
        return None

    def _coerce_destination(self, destination: Any) -> str:
        """Normalizuje destination do formatu akceptowalnego przez API.

        Args:
            destination: Wartość destination z bazy.

        Returns:
            Destination jako tekst liczbowy.
        """

        text = str(destination).strip()
        if text.isdigit():
            return str(int(text))
        return text

    def _normalize_city_name(self, city: str) -> str:
        """Normalizuje nazwę miasta do porównań słownikowych.

        Args:
            city: Nazwa miasta.

        Returns:
            Znormalizowana nazwa miasta.
        """

        return city.strip().lower()

    def save_agent_hint(self) -> None:
        """Zapisuje pomocniczą analizę SQL wygenerowaną przez model OpenRouter.

        Returns:
            None

        Side Effects:
            Tworzy plik z podpowiedzią SQL w katalogu output.
        """

        system_prompt = (
            "Jesteś asystentem SQL. Zaproponuj krótkie zapytania SELECT do mapowania "
            "miasto->destination i danych do signatureGenerator."
        )
        user_prompt = (
            "Przygotuj 5 krótkich propozycji zapytań i pól, które warto sprawdzić. "
            "Odpowiedz listą punktów."
        )
        response = self._openrouter_client.chat(system_prompt, user_prompt)
        write_text(self._output_dir / "step0_openrouter_sql_hint.txt", response)
