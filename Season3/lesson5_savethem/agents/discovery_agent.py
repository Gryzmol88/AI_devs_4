"""Agent discovery odpowiedzialny za wyszukiwanie narzędzi i zbieranie danych."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging
from urllib.parse import urljoin

from clients.openrouter_client import OpenRouterClient
from clients.tools_api_client import ToolsApiClient
from utils.output import write_json


@dataclass(slots=True)
class DiscoveryResult:
    """Przechowuje rezultat etapu discovery.

    Atrybuty:
        discovered_tools: Lista wykrytych endpointów narzędzi.
        raw_payloads: Surowe odpowiedzi z `toolsearch` i narzędzi.
    """

    discovered_tools: list[str]
    raw_payloads: dict[str, Any]


@dataclass(slots=True)
class DiscoveryAgent:
    """Realizuje iteracyjne odkrywanie narzędzi i pobieranie wiedzy.

    Atrybuty:
        tools_client: Klient huba i narzędzi.
        openrouter_client: Klient LLM generujący kolejne query.
        logger: Logger terminalowy.
        iterations: Maksymalna liczba rund discovery.
        max_tool_calls_per_iteration: Limit wywołań narzędzi na rundę.
    """

    tools_client: ToolsApiClient
    openrouter_client: OpenRouterClient
    logger: logging.Logger
    iterations: int
    max_tool_calls_per_iteration: int

    def run(self, session_dir: Path) -> DiscoveryResult:
        """Uruchamia pełny cykl discovery i zapisuje snapshoty do `output`.

        Args:
            session_dir: Katalog sesji, do którego zapisywane są wyniki pośrednie.

        Returns:
            Obiekt `DiscoveryResult` zawierający dane do dalszego przetwarzania.
        """

        base_queries = [
            "I need notes about movement rules and terrain",
            "I need a map for the savethem mission, including start and Skolwin destination.",
            "I need movement rules for terrain, obstacles and legal moves in savethem.",
            "I need vehicle list with speed, fuel usage and food usage per move in savethem.",
            "I need resource constraints, especially initial fuel and food amounts in savethem.",
        ]
        known_queries: list[str] = []
        discovered_tools: list[str] = []
        raw_payloads: dict[str, Any] = {"toolsearch": [], "tools": []}

        for iteration in range(self.iterations):
            self.logger.info("Discovery iteration %s/%s", iteration + 1, self.iterations)
            summary = self._build_summary(raw_payloads)
            dynamic_queries = self.openrouter_client.generate_discovery_queries(summary)
            planned_queries = base_queries + dynamic_queries

            for query in planned_queries:
                if query in known_queries:
                    continue
                known_queries.append(query)
                self.logger.info("toolsearch query: %s", query)
                toolsearch_response = self.tools_client.toolsearch(query)
                raw_payloads["toolsearch"].append({"query": query, "response": toolsearch_response})

                tool_urls = self._extract_tool_urls(toolsearch_response)
                for url in tool_urls:
                    if url not in discovered_tools:
                        discovered_tools.append(url)

            write_json(session_dir / f"step1_discovery_iteration_{iteration + 1}.json", raw_payloads)

            if not discovered_tools:
                continue

            call_budget = max(self.max_tool_calls_per_iteration, len(discovered_tools) * 4)
            tool_calls = 0
            for tool_url in discovered_tools:
                if tool_calls >= call_budget:
                    break
                for prompt in self._tool_prompts_for(tool_url):
                    if tool_calls >= call_budget:
                        break
                    self.logger.info("Tool call: %s", tool_url)
                    try:
                        tool_response = self.tools_client.tool_query(tool_url, prompt)
                        raw_payloads["tools"].append(
                            {"tool_url": tool_url, "query": prompt, "response": tool_response}
                        )
                    except RuntimeError as error:
                        self.logger.warning("Tool call failed (%s): %s", tool_url, error)
                        raw_payloads["tools"].append(
                            {"tool_url": tool_url, "query": prompt, "error": str(error)}
                        )
                    tool_calls += 1

            write_json(session_dir / f"step1_tools_iteration_{iteration + 1}.json", raw_payloads)

        return DiscoveryResult(discovered_tools=discovered_tools, raw_payloads=raw_payloads)

    def _build_summary(self, raw_payloads: dict[str, Any]) -> str:
        """Buduje skrót danych discovery używany jako kontekst dla OpenRouter.

        Args:
            raw_payloads: Zgromadzone odpowiedzi narzędzi.

        Returns:
            Krótki tekst podsumowujący stan discovery.
        """

        toolsearch_count = len(raw_payloads.get("toolsearch", []))
        tools_count = len(raw_payloads.get("tools", []))
        return (
            f"Toolsearch calls: {toolsearch_count}. "
            f"Tool calls: {tools_count}. "
            "Collect all required mission data to compute valid route."
        )

    def _extract_tool_urls(self, payload: dict[str, Any]) -> list[str]:
        """Wyszukuje adresy URL narzędzi w odpowiedzi `toolsearch`.

        Args:
            payload: Odpowiedź z `toolsearch`.

        Returns:
            Lista unikalnych URL-i wyglądających jak endpointy.
        """

        urls: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    lowered = str(key).lower()
                    if lowered in {"url", "endpoint", "api_url", "tool_url"} and isinstance(value, str):
                        cleaned = value.strip()
                        if not cleaned:
                            continue
                        resolved = cleaned
                        if cleaned.startswith("/"):
                            resolved = urljoin(self.tools_client.settings.toolsearch_url, cleaned)
                        elif not cleaned.startswith("http://") and not cleaned.startswith("https://"):
                            resolved = urljoin(self.tools_client.settings.toolsearch_url, f"/{cleaned}")
                        if resolved not in urls:
                            urls.append(resolved)
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(payload)
        return urls

    def _tool_prompts_for(self, tool_url: str) -> list[str]:
        """Zwraca listę pytań dopasowaną do konkretnego narzędzia.

        Returns:
            Lista zapytań w języku angielskim.
        """

        lowered = tool_url.lower()
        if "map" in lowered:
            return [
                "Skolwin",
            ]
        if "book" in lowered:
            return [
                "I need notes about movement rules and terrain",
                "How does movement work on water, rocks and trees?",
                "Can each vehicle traverse W R T tiles?",
                "vehicle selection and dismount rules",
            ]
        if "wehicle" in lowered or "vehicle" in lowered:
            return [
                "rocket",
                "horse",
                "walk",
                "car",
            ]
        return [
            "Return full map data, movement rules, vehicles and mission constraints.",
        ]
