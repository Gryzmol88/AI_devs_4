"""Deterministyczny runner misji pobocznej oparty o shell API."""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from command_policy import CommandPolicy
from config import Settings
from hints import german_butterfly_candidates
from io_utils import append_jsonl, log_terminal, timestamp_utc, write_json, write_text
from shell_api_client import ShellApiClient
from verify_client import VerifyClient


def _extract_strings(payload: Any) -> list[str]:
    """Rekurencyjnie zbiera teksty z dowolnej struktury danych.

    Args:
        payload: Obiekt wejsciowy (slownik, lista lub wartosc skalarna).

    Returns:
        Lista ciagow znakow odnalezionych w strukturze.
    """

    values: list[str] = []
    if isinstance(payload, str):
        values.append(payload)
    elif isinstance(payload, dict):
        for item in payload.values():
            values.extend(_extract_strings(item))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_extract_strings(item))
    return values


def _quote_arg_if_needed(value: str) -> str:
    """Zwraca argument gotowy do uzycia w komendzie shell.

    Args:
        value: Kandydat argumentu.

    Returns:
        Argument bez zmian lub ujety w cudzyslow, gdy zawiera spacje.
    """

    if " " not in value:
        return value
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def _normalize_unix_path(path: str) -> str:
    """Normalizuje sciezke do postaci unixowej.

    Args:
        path: Surowa sciezka.

    Returns:
        Znormalizowana sciezka bez koncowego ukosnika (poza `/`).
    """

    normalized = path.strip().replace("\\", "/")
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = "/" + normalized.lstrip("/")
    normalized = normalized.rstrip("/")
    return normalized or "/"


def _extract_command_paths(command: str) -> list[str]:
    """Wydobywa bezwzgledne sciezki z komendy shell.

    Args:
        command: Komenda shell.

    Returns:
        Lista sciezek znalezionych w komendzie.
    """

    matches = re.findall(r"/[A-Za-z0-9._/\-]*", command)
    return [_normalize_unix_path(match) for match in matches if _normalize_unix_path(match)]


def _safe_name_from_path(path: str) -> str:
    """Tworzy bezpieczna nazwe pliku na podstawie sciezki.

    Args:
        path: Oryginalna sciezka unixowa.

    Returns:
        Nazwa mozliwa do zapisu na dysku lokalnym.
    """

    normalized = _normalize_unix_path(path)
    if normalized == "/":
        return "root"
    trimmed = normalized.strip("/")
    return re.sub(r"[^A-Za-z0-9._-]+", "__", trimmed)


@dataclass(slots=True)
class SideMissionRunner:
    """Koordynuje przebieg misji pobocznej na podstawie hintu.

    Atrybuty:
        settings: Ustawienia aplikacji.
        shell_api: Klient shell API.
        verify_api: Klient verify API.
        policy: Polityka bezpieczenstwa komend.
        output_dir: Katalog artefaktow sesji.
    """

    settings: Settings
    shell_api: ShellApiClient
    verify_api: VerifyClient
    policy: CommandPolicy
    output_dir: Path

    @property
    def session_log_path(self) -> Path:
        """Zwraca sciezke pliku logu sesji.

        Returns:
            Sciezka pliku `session_log.jsonl`.
        """

        return self.output_dir / "session_log.jsonl"

    def _record_event(self, event: dict[str, Any]) -> None:
        """Dopisuje rekord zdarzenia do logu sesji.

        Args:
            event: Slownik danych zdarzenia.

        Efekty uboczne:
            Dopisuje linie do pliku `session_log.jsonl`.
        """

        append_jsonl(self.session_log_path, {"timestamp": timestamp_utc(), **event})

    def _extract_success_code(self, payload: Any) -> str | None:
        """Wykrywa poprawny kod odpowiedzi na podstawie regexu z konfiguracji.

        Args:
            payload: Odpowiedz narzedzia lub inna struktura danych.

        Returns:
            Znaleziony kod lub `None`.
        """

        pattern = re.compile(self.settings.side_task_success_regex)
        for text in _extract_strings(payload):
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    def _normalize_runtime_candidate(self, value: str) -> str | None:
        """Normalizuje kandydat hasla wykryty w odpowiedzi shell API.

        Args:
            value: Surowa wartosc tekstowa.

        Returns:
            Oczyszczony kandydat lub `None`, gdy wartosc nie nadaje sie do testu.
        """

        cleaned = value.strip().strip('"').strip("'")
        if not cleaned:
            return None
        if len(cleaned) > 120:
            return None
        if cleaned.endswith("/"):
            return None

        lowered = cleaned.lower()
        blocked_suffixes = (".txt", ".log", ".md", ".json", ".cfg")
        if lowered.endswith(blocked_suffixes):
            return None

        blocked_exact = {
            "directory listing.",
            "file content.",
            "available commands.",
            "invalid password.",
            "usage:",
        }
        if lowered in blocked_exact:
            return None

        if cleaned.startswith("/") and " " not in cleaned:
            return None
        return cleaned

    def _candidate_priority_for_command(self, command: str) -> int | None:
        """Wyznacza priorytet kandydatow na podstawie komendy zrodlowej.

        Args:
            command: Komenda shell.

        Returns:
            Priorytet (`0` najwyzszy) lub `None`, gdy komenda nie jest zrodlem hasla.
        """

        normalized = command.strip().lower().replace("\\", "/")
        if not normalized.startswith("cat "):
            return None
        if normalized.endswith("/notes/pass.txt"):
            return 0
        if normalized.endswith(".bash_history"):
            return 1
        return None

    def _extract_runtime_candidates_for_command(
        self, command: str, payload: Any
    ) -> list[str]:
        """Wydobywa kandydatow hasla tylko z istotnych komend `cat`.

        Args:
            command: Komenda, ktora zwrocila `payload`.
            payload: Struktura odpowiedzi shell API.

        Returns:
            Lista kandydatow do uruchomienia binarki.
        """

        priority = self._candidate_priority_for_command(command)
        if priority is None:
            return []

        discovered: list[str] = []
        seen: set[str] = set()
        explicit_pattern = re.compile(r"(?i)(?:pass(?:word)?|haslo)\s*[:=]\s*([^\s]+)")
        history_pattern = re.compile(
            r"(?i)/opt/firmware/cooler/cooler\.bin(?:\s+(\"[^\"]+\"|'[^']+'|[^\s]+))?\s*$"
        )
        blocked_history_args = {
            "show",
            "and",
            "short",
            "descriptions",
            "list",
            "files",
            "directories",
            "cat",
            "change",
            "current",
            "pwd",
            "print",
            "working",
            "remove",
            "virtual",
            "filesystem",
            "editline",
            "line-number",
            "replace",
            "one",
            "line",
            "text",
            "reboot",
            "rebuild",
            "state",
            "from",
            "disk",
            "date",
            "server",
            "time",
            "machine",
        }

        for text in _extract_strings(payload):
            for match in explicit_pattern.findall(text):
                normalized = self._normalize_runtime_candidate(match)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    discovered.append(normalized)

            if priority == 1:
                for line in text.splitlines():
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    history_match = history_pattern.search(line_stripped)
                    if not history_match:
                        continue
                    argument = history_match.group(1)
                    if argument is None:
                        continue
                    normalized = self._normalize_runtime_candidate(argument)
                    if not normalized:
                        continue
                    if normalized.lower() in blocked_history_args:
                        continue
                    if normalized not in seen:
                        seen.add(normalized)
                        discovered.append(normalized)
                        if len(discovered) >= 12:
                            break

            if priority == 0:
                for line in text.splitlines():
                    candidate = self._normalize_runtime_candidate(line)
                    if not candidate:
                        continue
                    if candidate not in seen:
                        seen.add(candidate)
                        discovered.append(candidate)

        return discovered

    def _extract_lock_file_path(self, result: dict[str, Any]) -> str | None:
        """Wydobywa sciezke lockfile z odpowiedzi binarki, jesli wystepuje.

        Args:
            result: Ustandaryzowany wynik pojedynczej komendy shell.

        Returns:
            Sciezka lockfile lub `None`.
        """

        response = result.get("response")
        if not isinstance(response, dict):
            return None
        data = response.get("data")
        if not isinstance(data, str):
            return None
        match = re.search(r"Lock file exists:\s*(/[^ \n\r\t]+)", data)
        if not match:
            return None
        return match.group(1).strip()

    def _register_path(
        self,
        path: str,
        seen_paths: set[str],
        seen_dirs: set[str],
        seen_files: set[str],
        is_dir: bool | None = None,
    ) -> None:
        """Rejestruje pojedyncza sciezke i jej typ.

        Args:
            path: Sciezka do zapisania.
            seen_paths: Zbior wszystkich napotkanych sciezek.
            seen_dirs: Zbior napotkanych katalogow.
            seen_files: Zbior napotkanych plikow.
            is_dir: Wymuszenie typu katalog/plik lub `None` do heurystyki.
        """

        normalized = _normalize_unix_path(path)
        if not normalized:
            return
        seen_paths.add(normalized)
        if normalized != "/":
            parent = _normalize_unix_path(normalized.rsplit("/", 1)[0] or "/")
            if parent:
                seen_paths.add(parent)
                seen_dirs.add(parent)

        if is_dir is True:
            seen_dirs.add(normalized)
            return
        if is_dir is False:
            seen_files.add(normalized)
            return

        if normalized == "/" or "." not in normalized.rsplit("/", 1)[-1]:
            seen_dirs.add(normalized)
        else:
            seen_files.add(normalized)

    def _collect_paths_from_result(
        self,
        result: dict[str, Any],
        seen_paths: set[str],
        seen_dirs: set[str],
        seen_files: set[str],
    ) -> None:
        """Zbiera sciezki z wyniku kroku shell.

        Args:
            result: Wynik pojedynczej komendy shell.
            seen_paths: Zbior wszystkich napotkanych sciezek.
            seen_dirs: Zbior napotkanych katalogow.
            seen_files: Zbior napotkanych plikow.
        """

        command = str(result.get("command", ""))
        for command_path in _extract_command_paths(command):
            self._register_path(command_path, seen_paths, seen_dirs, seen_files)

        response = result.get("response")
        if not isinstance(response, dict):
            return

        response_path = response.get("path")
        if isinstance(response_path, str) and response_path.strip():
            is_dir = response.get("code") == 120
            if response.get("code") == 150:
                is_dir = False
            self._register_path(response_path, seen_paths, seen_dirs, seen_files, is_dir=is_dir)

        base_path = response_path if isinstance(response_path, str) else None
        data = response.get("data")
        if not (isinstance(base_path, str) and isinstance(data, list) and response.get("code") == 120):
            return

        base_normalized = _normalize_unix_path(base_path)
        for entry in data:
            if not isinstance(entry, str):
                continue
            stripped = entry.strip()
            if not stripped:
                continue
            entry_is_dir = stripped.endswith("/")
            leaf = stripped.rstrip("/")
            child = _normalize_unix_path(f"{base_normalized}/{leaf}")
            self._register_path(
                child,
                seen_paths,
                seen_dirs,
                seen_files,
                is_dir=entry_is_dir,
            )

    def _format_paths_tree(self, seen_paths: set[str], seen_dirs: set[str]) -> str:
        """Buduje tekstowa reprezentacje drzewa sciezek.

        Args:
            seen_paths: Zbior wszystkich napotkanych sciezek.
            seen_dirs: Zbior napotkanych katalogow.

        Returns:
            Drzewo katalogow i plikow w formacie tekstowym.
        """

        tree: dict[str, dict[str, Any]] = {"_children": {}}
        ordered_paths = sorted(seen_paths, key=lambda item: (item.count("/"), item))

        for path in ordered_paths:
            if path == "/":
                continue
            parts = [part for part in path.strip("/").split("/") if part]
            node = tree
            current_path = ""
            for index, part in enumerate(parts):
                current_path = f"{current_path}/{part}"
                children = node.setdefault("_children", {})
                if part not in children:
                    children[part] = {"_children": {}}
                node = children[part]
                if current_path in seen_dirs:
                    node["_is_dir"] = True
                if index == len(parts) - 1 and current_path not in seen_dirs:
                    node["_is_dir"] = False

        lines: list[str] = ["/"]

        def _walk(node: dict[str, Any], prefix: str = "") -> None:
            children = node.get("_children", {})
            names = sorted(children.keys())
            for position, name in enumerate(names):
                child = children[name]
                is_last = position == len(names) - 1
                branch = "└─ " if is_last else "├─ "
                child_prefix = "   " if is_last else "│  "
                is_dir = bool(child.get("_is_dir", True))
                label = f"{name}/" if is_dir else name
                lines.append(f"{prefix}{branch}{label}")
                _walk(child, prefix + child_prefix)

        _walk(tree)
        return "\n".join(lines) + "\n"

    def _is_forbidden_path(self, path: str) -> bool:
        """Sprawdza, czy sciezka jest zabroniona przez polityke.

        Args:
            path: Sciezka do sprawdzenia.

        Returns:
            `True`, gdy sciezka jest zabroniona.
        """

        normalized = _normalize_unix_path(path)
        for forbidden in self.policy.forbidden_paths:
            blocked = _normalize_unix_path(forbidden)
            if normalized == blocked or normalized.startswith(f"{blocked}/"):
                return True
        return False

    def _discover_full_filesystem(
        self,
        seen_paths: set[str],
        seen_dirs: set[str],
        seen_files: set[str],
        start_step: int,
    ) -> tuple[dict[str, Any], int]:
        """Skanuje strukture filesystemu przez BFS poza sciezkami zabronionymi.

        Args:
            seen_paths: Zbior wszystkich napotkanych sciezek.
            seen_dirs: Zbior napotkanych katalogow.
            seen_files: Zbior napotkanych plikow.
            start_step: Numer kroku startowego.

        Returns:
            Krotka `(summary_discovery, ostatni_krok)`.
        """

        max_dirs = max(1, self.settings.discover_max_dirs)
        queue: deque[str] = deque(["/"])
        visited: set[str] = set()
        enqueued: set[str] = {"/"}
        step = start_step
        scanned_count = 0
        errors_count = 0

        while queue and scanned_count < max_dirs:
            current_dir = _normalize_unix_path(queue.popleft())
            if not current_dir or current_dir in visited:
                continue
            visited.add(current_dir)

            if self._is_forbidden_path(current_dir):
                continue

            step += 1
            command = f"ls {current_dir}"
            log_terminal(f"Discovery {scanned_count + 1}/{max_dirs}: {command}")
            result, extra_events, _, _ = self._run_single_step(step=step, command=command)
            self._collect_paths_from_result(result, seen_paths, seen_dirs, seen_files)
            for event in extra_events:
                payload = event.get("payload")
                if isinstance(payload, dict):
                    self._collect_paths_from_result(payload, seen_paths, seen_dirs, seen_files)

            scanned_count += 1
            if not result.get("ok"):
                errors_count += 1
                continue

            response = result.get("response")
            if not isinstance(response, dict):
                continue
            if response.get("code") != 120:
                continue

            base_path = response.get("path")
            entries = response.get("data")
            if not (isinstance(base_path, str) and isinstance(entries, list)):
                continue

            base_normalized = _normalize_unix_path(base_path)
            for entry in entries:
                if not isinstance(entry, str) or not entry.strip():
                    continue
                if not entry.endswith("/"):
                    continue
                child_dir = _normalize_unix_path(f"{base_normalized}/{entry.rstrip('/')}")
                if not child_dir or child_dir in enqueued:
                    continue
                if self._is_forbidden_path(child_dir):
                    continue
                queue.append(child_dir)
                enqueued.add(child_dir)

        summary = {
            "enabled": True,
            "max_dirs": max_dirs,
            "scanned_dirs": scanned_count,
            "visited_dirs": len(visited),
            "errors": errors_count,
            "completed": not bool(queue),
            "remaining_queue": len(queue),
        }
        return summary, step

    def _maybe_update_gitignore(self, command: str, response: dict[str, Any]) -> None:
        """Aktualizuje reguly `.gitignore` po odczycie pliku.

        Args:
            command: Komenda wykonana w shell API.
            response: Odpowiedz shell API.
        """

        if ".gitignore" not in command:
            return
        path = str(response.get("path", "")).replace("\\", "/").strip()
        if not path.endswith(".gitignore"):
            return
        base_dir = path.rsplit("/", 1)[0] or "/"
        data = response.get("data")
        if isinstance(data, str):
            entries = data.splitlines()
        elif isinstance(data, list):
            entries = [str(item) for item in data]
        else:
            entries = []
        self.policy.update_blocked_entries(entries=entries, base_dir=base_dir)

    def _run_shell_command(self, command: str) -> dict[str, Any]:
        """Uruchamia komende shell z walidacja polityki bezpieczenstwa.

        Args:
            command: Komenda do uruchomienia.

        Returns:
            Ustandaryzowany wynik wykonania komendy.
        """

        allowed, reason, bootstrap_command = self.policy.validate(command)
        if not allowed:
            return {
                "ok": False,
                "blocked": True,
                "command": command,
                "reason": reason,
                "required_bootstrap_command": bootstrap_command,
            }

        normalized = command.strip().replace("\\", "/")
        if normalized.startswith("cat ") and normalized.endswith("/.gitignore"):
            gitignore_path = normalized[4:].strip()
            base_dir = gitignore_path.rsplit("/", 1)[0] or "/"
            self.policy.mark_gitignore_checked(base_dir)

        shell_result = self.shell_api.run_command(command)
        if not shell_result.get("ok", False):
            result = {
                "ok": False,
                "blocked": False,
                "command": command,
                "error": shell_result.get("error_message"),
                "http_status": shell_result.get("http_status"),
                "error_code": shell_result.get("error_code"),
                "ban": shell_result.get("ban"),
                "is_ban": shell_result.get("is_ban", False),
                "is_retryable": shell_result.get("is_retryable", False),
            }
            if self.settings.stop_on_ban and result.get("is_ban"):
                result["stop_agent"] = True
                result["stop_reason"] = "Wykryto ban VM. Sesja zostala zatrzymana."
            return result

        response = shell_result.get("response", {})
        self._maybe_update_gitignore(command, response)
        success_code = self._extract_success_code(response)
        return {
            "ok": True,
            "blocked": False,
            "command": command,
            "response": response,
            "detected_success_code": success_code,
        }

    def _build_execution_commands_with_dynamic_candidates(
        self, dynamic_candidates: list[str]
    ) -> list[str]:
        """Buduje komendy uruchomieniowe z priorytetem kandydatow dynamicznych.

        Args:
            dynamic_candidates: Kandydaci odkryci w trakcie rekonesansu.

        Returns:
            Lista komend shell do uruchomienia binarki.
        """

        binary_path = self.settings.side_task_binary_path
        commands: list[str] = [binary_path]

        ordered_candidates: list[str] = []
        seen_candidates: set[str] = set()
        low_priority_hints = german_butterfly_candidates()[:10]
        for candidate in dynamic_candidates + low_priority_hints:
            normalized = self._normalize_runtime_candidate(candidate)
            if not normalized or normalized in seen_candidates:
                continue
            seen_candidates.add(normalized)
            ordered_candidates.append(normalized)

        for candidate in ordered_candidates:
            commands.append(f"{binary_path} {_quote_arg_if_needed(candidate)}")
        return commands

    def _execute_with_bootstrap(
        self, step: int, command: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Wykonuje komende z bootstrapem `.gitignore`, jesli jest wymagany.

        Args:
            step: Numer kroku glownej petli.
            command: Komenda docelowa.

        Returns:
            Krotka `(wynik_koncowy, dodatkowe_zdarzenia)`.
        """

        extra_events: list[dict[str, Any]] = []
        initial = self._run_shell_command(command)
        if not (
            initial.get("blocked")
            and isinstance(initial.get("required_bootstrap_command"), str)
            and initial.get("required_bootstrap_command")
        ):
            return initial, extra_events

        bootstrap_command = str(initial["required_bootstrap_command"]).strip()
        log_terminal(f"Krok {step}: bootstrap -> {bootstrap_command}")
        bootstrap_result = self._run_shell_command(bootstrap_command)
        write_json(
            self.output_dir / f"step{step:02d}_tool01_bootstrap.json",
            bootstrap_result,
        )
        extra_events.append(
            {
                "type": "bootstrap_result",
                "step": step,
                "bootstrap_command": bootstrap_command,
                "payload": bootstrap_result,
            }
        )

        log_terminal(f"Krok {step}: retry -> {command}")
        retried = self._run_shell_command(command)
        retried["bootstrap_applied"] = True
        retried["bootstrap_command"] = bootstrap_command
        write_json(
            self.output_dir / f"step{step:02d}_tool01_retry.json",
            retried,
        )
        extra_events.append(
            {
                "type": "retry_result",
                "step": step,
                "original_command": command,
                "payload": retried,
            }
        )
        return retried, extra_events

    def _run_single_step(
        self, step: int, command: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool, str | None]:
        """Uruchamia pojedynczy krok shella i zapisuje artefakty kroku.

        Args:
            step: Numer kroku.
            command: Komenda shell.

        Returns:
            Krotka `(result, extra_events, stop_session, stop_reason)`.
        """

        log_terminal(f"Krok {step}/{self.settings.max_steps}: shell -> {command}")
        result, extra_events = self._execute_with_bootstrap(step=step, command=command)

        write_json(self.output_dir / f"step{step:02d}_tool01_shell.json", result)
        self._record_event({"type": "tool_result", "step": step, "tool_name": "shell", "payload": result})
        for event in extra_events:
            self._record_event(event)

        if result.get("stop_agent"):
            return result, extra_events, True, str(result.get("stop_reason", "Zatrzymano sesje."))
        return result, extra_events, False, None

    def _capture_seen_file_contents(
        self,
        seen_files: set[str],
        seen_paths: set[str],
        seen_dirs: set[str],
        max_files: int,
        max_chars: int,
        start_step: int,
    ) -> tuple[dict[str, Any], int]:
        """Zapisuje tresci napotkanych plikow do katalogu sesji.

        Args:
            seen_files: Zbior plikow wykrytych w trakcie sesji.
            seen_paths: Zbior wszystkich napotkanych sciezek.
            seen_dirs: Zbior napotkanych katalogow.
            max_files: Limit liczby plikow do odczytu.
            max_chars: Limit znakow tresci na plik.
            start_step: Numer kroku startowego dla logowania.

        Returns:
            Krotka `(indeks_capture, ostatni_krok)`.
        """

        capture_dir = self.output_dir / "files_content"
        capture_dir.mkdir(parents=True, exist_ok=True)

        index: dict[str, Any] = {
            "enabled": True,
            "max_files": max_files,
            "max_chars": max_chars,
            "captured": [],
        }
        step = start_step
        candidates = sorted(path for path in seen_files if path and path != "/")

        for file_path in candidates:
            if len(index["captured"]) >= max_files:
                index["captured"].append(
                    {"path": file_path, "status": "skipped_limit", "reason": "max_files"}
                )
                continue

            step += 1
            cat_command = f"cat {file_path}"
            log_terminal(f"Capture {len(index['captured']) + 1}/{max_files}: {cat_command}")
            result, extra_events = self._execute_with_bootstrap(step=step, command=cat_command)

            write_json(self.output_dir / f"capture_step{step:03d}_shell.json", result)
            self._record_event(
                {"type": "capture_result", "step": step, "tool_name": "shell", "payload": result}
            )
            self._collect_paths_from_result(result, seen_paths, seen_dirs, seen_files)
            for event in extra_events:
                self._record_event(event)
                payload = event.get("payload")
                if isinstance(payload, dict):
                    self._collect_paths_from_result(payload, seen_paths, seen_dirs, seen_files)

            if not result.get("ok"):
                index["captured"].append(
                    {
                        "path": file_path,
                        "status": "error",
                        "http_status": result.get("http_status"),
                        "error_code": result.get("error_code"),
                        "error": result.get("error"),
                    }
                )
                continue

            response = result.get("response", {})
            data = response.get("data") if isinstance(response, dict) else None
            if isinstance(data, list):
                content = "\n".join(str(item) for item in data)
            elif isinstance(data, str):
                content = data
            else:
                content = json.dumps(data, ensure_ascii=False)

            truncated = False
            if len(content) > max_chars:
                content = content[:max_chars]
                truncated = True

            file_name = f"{_safe_name_from_path(file_path)}.json"
            payload = {
                "path": file_path,
                "source_command": cat_command,
                "truncated": truncated,
                "max_chars": max_chars,
                "content": content,
            }
            write_json(capture_dir / file_name, payload)
            index["captured"].append(
                {
                    "path": file_path,
                    "status": "ok",
                    "content_file": f"files_content/{file_name}",
                    "truncated": truncated,
                    "size_chars": len(content),
                }
            )

        return index, step

    def run(self) -> dict[str, Any]:
        """Uruchamia pelny proces misji pobocznej.

        Returns:
            Podsumowanie wykonania sesji.

        Efekty uboczne:
            Zapisuje pliki krokow i wynik koncowy w katalogu sesji.
        """

        success_code: str | None = None
        verify_response: dict[str, Any] | None = None
        stop_reason: str | None = None
        stopped_due_to_ban = False
        discovered_candidates: list[str] = []
        discovered_candidate_priority: dict[str, int] = {}
        seen_paths: set[str] = set()
        seen_dirs: set[str] = set()
        seen_files: set[str] = set()

        step = 0
        for command in self.settings.get_pre_commands():
            if step >= self.settings.max_steps:
                break
            step += 1
            result, extra_events, should_stop, stop_reason = self._run_single_step(
                step=step, command=command
            )
            self._collect_paths_from_result(result, seen_paths, seen_dirs, seen_files)
            for event in extra_events:
                payload = event.get("payload")
                if isinstance(payload, dict):
                    self._collect_paths_from_result(payload, seen_paths, seen_dirs, seen_files)
            if should_stop:
                stopped_due_to_ban = True
                break

            if result.get("ok"):
                response_payload = result.get("response", {})
                data_payload = (
                    response_payload.get("data", response_payload)
                    if isinstance(response_payload, dict)
                    else response_payload
                )
                extracted = self._extract_runtime_candidates_for_command(command, data_payload)
                priority = self._candidate_priority_for_command(command)
                new_candidates = [item for item in extracted if item not in discovered_candidates]
                if new_candidates:
                    discovered_candidates.extend(new_candidates)
                    if priority is not None:
                        for candidate in new_candidates:
                            current = discovered_candidate_priority.get(candidate, priority)
                            discovered_candidate_priority[candidate] = min(current, priority)
                    preview = ", ".join(new_candidates[:4])
                    label = "high" if priority == 0 else "medium"
                    log_terminal(f"Krok {step}: wykryte kandydaty ({label}) -> {preview}")

            detected = result.get("detected_success_code")
            if isinstance(detected, str) and detected.strip():
                success_code = detected.strip()
                log_terminal(f"Wykryto kod sukcesu: {success_code}")
                if self.settings.side_task_auto_submit:
                    verify_response = self.verify_api.submit_answer(success_code)
                    write_json(self.output_dir / f"step{step:02d}_verify_response.json", verify_response)
                    self._record_event({"type": "verify_response", "step": step, "payload": verify_response})
                break

        if not success_code and not stopped_due_to_ban and step < self.settings.max_steps:
            candidate_order = {value: index for index, value in enumerate(discovered_candidates)}
            ordered_dynamic = sorted(
                discovered_candidates,
                key=lambda item: (
                    discovered_candidate_priority.get(item, 9),
                    candidate_order.get(item, 9999),
                ),
            )
            execution_commands = self._build_execution_commands_with_dynamic_candidates(
                ordered_dynamic
            )
            deduplicated_exec: list[str] = []
            seen_exec: set[str] = set()
            for item in execution_commands:
                normalized = item.strip()
                if normalized and normalized not in seen_exec:
                    deduplicated_exec.append(normalized)
                    seen_exec.add(normalized)

            for command in deduplicated_exec:
                if step >= self.settings.max_steps:
                    break
                step += 1
                result, extra_events, should_stop, stop_reason = self._run_single_step(
                    step=step, command=command
                )
                self._collect_paths_from_result(result, seen_paths, seen_dirs, seen_files)
                for event in extra_events:
                    payload = event.get("payload")
                    if isinstance(payload, dict):
                        self._collect_paths_from_result(payload, seen_paths, seen_dirs, seen_files)
                if should_stop:
                    stopped_due_to_ban = True
                    break

                lock_file_path = self._extract_lock_file_path(result)
                if lock_file_path and step < self.settings.max_steps:
                    unlock_command = f"rm {lock_file_path}"
                    step += 1
                    log_terminal(f"Krok {step}: wykryto lockfile, odblokowanie -> {unlock_command}")
                    unlock_result, unlock_extra_events, should_stop, stop_reason = self._run_single_step(
                        step=step, command=unlock_command
                    )
                    self._collect_paths_from_result(
                        unlock_result, seen_paths, seen_dirs, seen_files
                    )
                    for event in unlock_extra_events:
                        payload = event.get("payload")
                        if isinstance(payload, dict):
                            self._collect_paths_from_result(
                                payload, seen_paths, seen_dirs, seen_files
                            )
                    if should_stop:
                        stopped_due_to_ban = True
                        break

                    if unlock_result.get("ok") and step < self.settings.max_steps:
                        step += 1
                        log_terminal(f"Krok {step}: ponowienie po odblokowaniu -> {command}")
                        result, extra_events, should_stop, stop_reason = self._run_single_step(
                            step=step, command=command
                        )
                        self._collect_paths_from_result(result, seen_paths, seen_dirs, seen_files)
                        for event in extra_events:
                            payload = event.get("payload")
                            if isinstance(payload, dict):
                                self._collect_paths_from_result(
                                    payload, seen_paths, seen_dirs, seen_files
                                )
                        if should_stop:
                            stopped_due_to_ban = True
                            break

                detected = result.get("detected_success_code")
                if isinstance(detected, str) and detected.strip():
                    success_code = detected.strip()
                    log_terminal(f"Wykryto kod sukcesu: {success_code}")
                    if self.settings.side_task_auto_submit:
                        verify_response = self.verify_api.submit_answer(success_code)
                        write_json(self.output_dir / f"step{step:02d}_verify_response.json", verify_response)
                        self._record_event({"type": "verify_response", "step": step, "payload": verify_response})
                    break

        mission_steps = step
        discovery_summary: dict[str, Any] = {"enabled": bool(self.settings.discover_full_fs)}
        if self.settings.discover_full_fs:
            discovery_summary, step = self._discover_full_filesystem(
                seen_paths=seen_paths,
                seen_dirs=seen_dirs,
                seen_files=seen_files,
                start_step=step,
            )

        capture_index: dict[str, Any] = {
            "enabled": bool(self.settings.capture_file_contents),
            "captured": [],
        }
        if self.settings.capture_file_contents:
            capture_index, step = self._capture_seen_file_contents(
                seen_files=seen_files,
                seen_paths=seen_paths,
                seen_dirs=seen_dirs,
                max_files=max(0, self.settings.capture_max_files),
                max_chars=max(200, self.settings.capture_max_chars),
                start_step=step,
            )

        summary = {
            "success": bool(success_code),
            "task": self.settings.side_task_name,
            "answer_key": self.settings.side_task_answer_key,
            "detected_code": success_code,
            "verify_response": verify_response,
            "stopped_due_to_ban": stopped_due_to_ban,
            "stop_reason": stop_reason,
            "discovered_candidates": discovered_candidates,
            "discovered_candidate_priority": discovered_candidate_priority,
            "paths_seen_count": len(seen_paths),
            "tested_commands": mission_steps,
            "discovery_enabled": bool(self.settings.discover_full_fs),
            "discovery_scanned_dirs": discovery_summary.get("scanned_dirs", 0),
            "capture_enabled": bool(self.settings.capture_file_contents),
            "capture_files_attempted": len(capture_index.get("captured", [])),
            "total_steps_with_capture": step,
        }

        paths_payload = {
            "all_paths": sorted(seen_paths),
            "directories": sorted(seen_dirs),
            "files": sorted(seen_files),
        }
        write_json(self.output_dir / "paths_seen.json", paths_payload)
        write_text(self.output_dir / "paths_tree.txt", self._format_paths_tree(seen_paths, seen_dirs))
        write_json(self.output_dir / "filesystem_discovery.json", discovery_summary)
        write_json(self.output_dir / "files_content_index.json", capture_index)

        write_json(self.output_dir / "final_result.json", summary)
        write_text(
            self.output_dir / "final_result.txt",
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
        return summary
