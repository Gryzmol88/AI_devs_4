"""Klient read-only do odczytu danych z panelu webowego OKO."""

import re
from html import unescape
from urllib.parse import urljoin

import requests

from config import AppSettings
from utils.logger import log_info, log_warn


class OkoPanelReader:
    """Pobiera dane z panelu OKO bez wykonywania modyfikacji.

    Args:
        settings: Konfiguracja aplikacji.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje czytnik panelu.

        Args:
            settings: Obiekt konfiguracji aplikacji.
        """

        self._settings = settings
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "okoeditor-readonly/1.0",
            }
        )

    def fetch_snapshot(self) -> dict:
        """Pobiera snapshot HTML i metadanych z panelu.

        Returns:
            Słownik zawierający listę źródeł HTML oraz rekordów zidentyfikowanych
            przez analizę tekstu strony.
        """

        auth = self._try_login()

        sources: list[dict] = []
        for url in self._candidate_urls():
            try:
                response = self._session.get(url, timeout=self._settings.app_timeout_seconds)
            except requests.RequestException as exc:
                sources.append({"url": url, "ok": False, "error": str(exc)})
                continue

            sources.append(
                {
                    "url": url,
                    "ok": response.ok,
                    "status_code": response.status_code,
                    "text": response.text if response.ok else "",
                    "is_login_page": self._is_login_page(response.text if response.ok else ""),
                }
            )

        detail_urls = self._extract_detail_urls(sources=sources)
        detail_sources = self._fetch_sources(urls=detail_urls)
        all_sources = sources + detail_sources

        records = self._extract_records(sources=all_sources)
        return {
            "auth": auth,
            "sources": all_sources,
            "detail_urls": detail_urls,
            "records": records,
        }

    def _try_login(self) -> dict:
        """Próbuje uwierzytelnić sesję do panelu.

        Returns:
            Metadane dotyczące przebiegu logowania.

        Side Effects:
            Wykonuje żądania HTTP GET/POST, aby uzyskać sesję.
        """

        panel_url = self._settings.oko_panel_url.rstrip("/")
        try:
            initial = self._session.get(panel_url, timeout=self._settings.app_timeout_seconds)
        except requests.RequestException as exc:
            return {"ok": False, "method": "GET", "url": panel_url, "error": str(exc)}

        if initial.ok and not self._is_login_page(initial.text):
            log_info("Sesja panelu jest już uwierzytelniona.")
            return {"ok": True, "method": "existing_session", "url": panel_url}

        login_payload = {
            "action": "login",
            "login": self._settings.oko_login,
            "password": self._settings.oko_password,
            "access_key": self._settings.aidevs_api_key,
        }
        login_urls = [
            panel_url,
            f"{panel_url}/incydenty",
            f"{panel_url}/zadania",
            f"{panel_url}/notatki",
        ]

        for login_url in login_urls:
            try:
                response = self._session.post(
                    login_url,
                    data=login_payload,
                    timeout=self._settings.app_timeout_seconds,
                    allow_redirects=True,
                )
            except requests.RequestException:
                continue

            if response.ok and not self._is_login_page(response.text):
                log_info(f"Logowanie do panelu potwierdzone: {login_url}")
                return {"ok": True, "method": "form_post", "url": login_url}

        log_warn("Nie udało się potwierdzić logowania do panelu; snapshot może zawierać tylko ekran logowania.")
        return {"ok": False, "method": "form_post", "url": panel_url}

    def _candidate_urls(self) -> list[str]:
        """Buduje listę adresów do odczytu danych panelu.

        Returns:
            Lista URL-i potencjalnie zawierających rekordy.
        """

        panel_url = self._settings.oko_panel_url.rstrip("/") + "/"
        urls = [
            panel_url,
            urljoin(panel_url, "?page=incydenty"),
            urljoin(panel_url, "?page=zadania"),
            urljoin(panel_url, "?page=notatki"),
            urljoin(panel_url, "incydenty"),
            urljoin(panel_url, "zadania"),
            urljoin(panel_url, "notatki"),
            urljoin(panel_url, "api/incydenty"),
            urljoin(panel_url, "api/zadania"),
            urljoin(panel_url, "api/notatki"),
        ]
        # Zachowujemy kolejność i usuwamy duplikaty.
        return list(dict.fromkeys(urls))

    def _extract_detail_urls(self, sources: list[dict]) -> list[str]:
        """Wydobywa URL-e stron szczegółowych rekordów.

        Args:
            sources: Lista odpowiedzi pobranych z panelu.

        Returns:
            Lista unikalnych adresów prowadzących do szczegółów rekordów.
        """

        panel_url = self._settings.oko_panel_url.rstrip("/") + "/"
        pattern = re.compile(r'href=["\'](/(?:incydenty|zadania|notatki)/[a-fA-F0-9]{32})["\']')
        urls: list[str] = []
        for source in sources:
            text = source.get("text", "") or ""
            if not text:
                continue
            for match in pattern.finditer(text):
                relative_url = match.group(1)
                urls.append(urljoin(panel_url, relative_url.lstrip("/")))

        # Limit ochronny, by nie wykonywać nadmiarowych requestów.
        return list(dict.fromkeys(urls))[:80]

    def _fetch_sources(self, urls: list[str]) -> list[dict]:
        """Pobiera listę źródeł URL i zwraca odpowiedzi w formacie snapshotu.

        Args:
            urls: Adresy do pobrania.

        Returns:
            Lista słowników opisujących odpowiedzi HTTP.
        """

        sources: list[dict] = []
        for url in urls:
            try:
                response = self._session.get(url, timeout=self._settings.app_timeout_seconds)
            except requests.RequestException as exc:
                sources.append({"url": url, "ok": False, "error": str(exc)})
                continue

            sources.append(
                {
                    "url": url,
                    "ok": response.ok,
                    "status_code": response.status_code,
                    "text": response.text if response.ok else "",
                    "is_login_page": self._is_login_page(response.text if response.ok else ""),
                }
            )
        return sources

    def _extract_records(self, sources: list[dict]) -> list[dict]:
        """Wydobywa rekordy z odpowiedzi HTML/JSON.

        Args:
            sources: Lista źródeł tekstu pozyskanych z panelu.

        Returns:
            Lista rekordów zawierających `id`, możliwą stronę i kontekst tekstowy.
        """

        id_regex = re.compile(r"\b[a-fA-F0-9]{32}\b")
        id_in_url_regex = re.compile(r"/(?:incydenty|zadania|notatki)/([a-fA-F0-9]{32})")
        records_map: dict[tuple[str, str], dict] = {}

        for source in sources:
            text = source.get("text", "") or ""
            if not text:
                continue

            lowered = text.lower()
            plain_text = self._extract_plain_text(text=text).lower()
            default_page = self._infer_page_from_url(source.get("url", ""))
            if default_page == "unknown":
                if "incydent" in lowered:
                    default_page = "incydenty"
                elif "zadani" in lowered:
                    default_page = "zadania"
                elif "notatk" in lowered:
                    default_page = "notatki"

            ids: set[str] = set(match.group(0).lower() for match in id_regex.finditer(text))
            url = str(source.get("url", ""))
            url_match = id_in_url_regex.search(url)
            if url_match:
                ids.add(url_match.group(1).lower())

            for record_id in ids:
                snippet = self._snippet_for_record(text=text, record_id=record_id, fallback_plain=plain_text)
                snippet_lower = snippet.lower()
                page = self._infer_page_from_snippet(snippet_lower, default_page=default_page)
                key = (record_id, page)
                is_detail_source = bool(url_match and url_match.group(1).lower() == record_id)
                source_text = plain_text if is_detail_source else self._compact_snippet(snippet)

                existing = records_map.get(key)
                if existing is None:
                    records_map[key] = {
                        "id": record_id,
                        "page": page,
                        "url": source.get("url"),
                        "snippet": self._compact_snippet(snippet),
                        "search_text": source_text,
                        "has_skolwin": "skolwin" in source_text.lower(),
                        "has_komarowo": "komarow" in source_text.lower(),
                    }
                    continue

                existing["search_text"] = self._compact_snippet(
                    f"{existing.get('search_text', '')} {source_text}"
                )
                existing["has_skolwin"] = bool(existing.get("has_skolwin") or ("skolwin" in source_text.lower()))
                existing["has_komarowo"] = bool(existing.get("has_komarowo") or ("komarow" in source_text.lower()))

        return list(records_map.values())

    def _infer_page_from_url(self, url: str) -> str:
        """Wnioskuje typ strony na podstawie adresu URL.

        Args:
            url: Adres źródła danych.

        Returns:
            Nazwa strony (`incydenty`, `zadania`, `notatki` lub `unknown`).
        """

        lowered = (url or "").lower()
        if "incydent" in lowered:
            return "incydenty"
        if "zadani" in lowered:
            return "zadania"
        if "notatk" in lowered:
            return "notatki"
        return "unknown"

    def _infer_page_from_snippet(self, snippet: str, default_page: str) -> str:
        """Wnioskuje typ strony na podstawie fragmentu tekstu.

        Args:
            snippet: Fragment tekstu wokół rekordu.
            default_page: Domyślna strona wywnioskowana z URL.

        Returns:
            Nazwa strony docelowej.
        """

        if "incydent" in snippet:
            return "incydenty"
        if "zadani" in snippet:
            return "zadania"
        if "notatk" in snippet:
            return "notatki"
        return default_page

    def _compact_snippet(self, snippet: str) -> str:
        """Normalizuje biały znak we fragmencie tekstu.

        Args:
            snippet: Surowy fragment tekstu.

        Returns:
            Skrócony tekst jednolinijkowy.
        """

        return " ".join(snippet.split())

    def _extract_plain_text(self, text: str) -> str:
        """Usuwa style/skrypty i tagi HTML, zostawiając samą treść.

        Args:
            text: Surowa treść HTML.

        Returns:
            Oczyszczony tekst możliwy do przeszukiwania słowami kluczowymi.
        """

        without_styles = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        without_scripts = re.sub(r"<script[\s\S]*?</script>", " ", without_styles, flags=re.IGNORECASE)
        without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
        return unescape(self._compact_snippet(without_tags))

    def _snippet_for_record(self, text: str, record_id: str, fallback_plain: str) -> str:
        """Buduje fragment tekstu dla konkretnego rekordu.

        Args:
            text: Surowa treść źródłowa.
            record_id: ID rekordu.
            fallback_plain: Oczyszczona treść strony bez HTML.

        Returns:
            Fragment tekstu przy rekordzie lub fallback na treść strony.
        """

        index = text.lower().find(record_id.lower())
        if index == -1:
            return fallback_plain[:1400]

        start = max(0, index - 420)
        end = min(len(text), index + 420)
        return text[start:end]

    def _is_login_page(self, text: str) -> bool:
        """Sprawdza, czy odpowiedź HTML przedstawia formularz logowania.

        Args:
            text: Treść HTML odpowiedzi.

        Returns:
            `True`, gdy wykryto charakterystyczne elementy strony logowania.
        """

        lowered = (text or "").lower()
        return (
            "logowanie operatora" in lowered
            and "name=\"access_key\"" in lowered
            and "name=\"password\"" in lowered
        )
