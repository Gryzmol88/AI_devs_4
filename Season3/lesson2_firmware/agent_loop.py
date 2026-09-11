"""Główna pętla agentowa dla zadania firmware."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from command_policy import CommandPolicy
from config import Settings
from io_utils import append_jsonl, log_terminal, timestamp_utc, write_json, write_text
from openrouter_client import OpenRouterClient
from shell_api_client import ShellApiClient
from verify_client import VerifyClient

ECCS_PATTERN = re.compile(r"ECCS-[A-Za-z0-9]{40}")


def _extract_strings(payload: Any) -> list[str]:
    """Rekurencyjnie zbiera wszystkie wartości tekstowe z dowolnego obiektu.

    Args:
        payload: Struktura danych JSON, lista lub wartość skalarna.

    Returns:
        Lista tekstów znalezionych w przekazanej strukturze.
    """

    collected: list[str] = []
    if isinstance(payload, str):
        collected.append(payload)
    elif isinstance(payload, dict):
        for value in payload.values():
            collected.extend(_extract_strings(value))
    elif isinstance(payload, list):
        for item in payload:
            collected.extend(_extract_strings(item))
    return collected


def _safe_json_loads(raw: str) -> dict[str, Any]:
    """Parsuje JSON argumentów narzędzia i zwraca słownik.

    Args:
        raw: Tekstowy JSON argumentów.

    Returns:
        Słownik argumentów; pusty słownik przy błędzie parsowania.
    """

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _truncate_text(value: str, max_chars: int) -> str:
    """Przycina tekst do maksymalnej liczby znaków.

    Args:
        value: Tekst wejściowy.
        max_chars: Maksymalna długość wyniku.

    Returns:
        Tekst przycięty do limitu znaków.
    """

    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


@dataclass(slots=True)
class FirmwareAgentRunner:
    """Koordynuje działanie agenta i narzędzi shell/verify.

    Atrybuty:
        settings: Ustawienia aplikacji.
        openrouter: Klient modelu LLM.
        shell_api: Klient shell API.
        verify_api: Klient verify API.
        policy: Reguły bezpieczeństwa komend.
        output_dir: Katalog zapisów pośrednich i finalnych.
        prompts_dir: Katalog promptów.
        messages: Historia konwersacji przekazywana modelowi.
    """

    settings: Settings
    openrouter: OpenRouterClient
    shell_api: ShellApiClient
    verify_api: VerifyClient
    policy: CommandPolicy
    output_dir: Path
    prompts_dir: Path
    messages: list[dict[str, Any]] = field(default_factory=list)
    knows_admin_password: bool = False
    knows_settings_content: bool = False
    execution_mode: bool = False
    admin_password: str | None = None
    settings_ini_content: str | None = None
    forced_attempted_pass_file: bool = False
    forced_attempted_history: bool = False
    forced_attempted_remove_lock: bool = False
    forced_attempted_set_cooling_enabled: bool = False
    forced_attempted_disable_test_mode: bool = False
    forced_attempted_run_with_password: bool = False
    forced_attempted_run_without_password: bool = False

    @property
    def session_log_path(self) -> Path:
        """Zwraca ścieżkę pliku logu sesji.

        Returns:
            Ścieżka do `session_log.jsonl`.
        """

        return self.output_dir / "session_log.jsonl"

    def _load_system_prompt(self) -> str:
        """Wczytuje prompt systemowy z pliku.

        Returns:
            Treść promptu systemowego.
        """

        return (self.prompts_dir / "system_prompt.txt").read_text(encoding="utf-8")

    def _build_tools(self) -> list[dict[str, Any]]:
        """Buduje definicje narzędzi Function Calling.

        Returns:
            Lista narzędzi zgodnych z API chat completions.
        """

        return [
            {
                "type": "function",
                "function": {
                    "name": "shell",
                    "description": "Wykonuje jedną komendę shell na VM.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Pojedyncza komenda shell do wykonania.",
                            }
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_answer",
                    "description": "Wysyła finalny kod ECCS do endpointu verify.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "confirmation": {
                                "type": "string",
                                "description": "Kod potwierdzający w formacie ECCS-...",
                            }
                        },
                        "required": ["confirmation"],
                    },
                },
            },
        ]

    def _record_event(self, event: dict[str, Any]) -> None:
        """Dopisuje zdarzenie do logu sesji.

        Args:
            event: Dane zdarzenia do zapisania.

        Efekty uboczne:
            Dopisuje rekord do `session_log.jsonl`.
        """

        append_jsonl(
            self.session_log_path,
            {"timestamp": timestamp_utc(), **event},
        )

    def _extract_eccs_code(self, payload: Any) -> str | None:
        """Wyszukuje kod ECCS w dowolnej strukturze odpowiedzi.

        Args:
            payload: Dane odpowiedzi shell/verify/modelu.

        Returns:
            Kod ECCS, jeśli został znaleziony; w przeciwnym razie `None`.
        """

        for text in _extract_strings(payload):
            match = ECCS_PATTERN.search(text)
            if match:
                return match.group(0)
        return None

    def _maybe_update_gitignore(self, command: str, response: dict[str, Any]) -> None:
        """Aktualizuje listę blokowanych wpisów po odczycie `.gitignore`.

        Args:
            command: Komenda wykonana przez shell API.
            response: Odpowiedź shell API.
        """

        if ".gitignore" not in command:
            return

        gitignore_path = str(response.get("path", "")).replace("\\", "/").strip()
        if not gitignore_path.endswith(".gitignore"):
            return

        base_dir = gitignore_path.rsplit("/", 1)[0] or "/"
        extracted: list[str] = []
        data = response.get("data")
        if isinstance(data, str):
            extracted = data.splitlines()
        elif isinstance(data, list):
            extracted = [str(item) for item in data]
        else:
            return
        self.policy.update_blocked_entries(extracted, base_dir=base_dir)

    def _handle_shell_tool(self, command: str) -> dict[str, Any]:
        """Wykonuje narzędzie `shell` z walidacją polityki bezpieczeństwa.

        Args:
            command: Komenda shell do uruchomienia.

        Returns:
            Wynik działania narzędzia wraz z metadanymi.
        """

        if self.execution_mode and not self._is_execution_mode_command_allowed(command):
            return {
                "ok": False,
                "blocked": True,
                "reason": (
                    "Execution mode: dozwolone są tylko komendy finalizujące "
                    "(`editline settings.ini`, `cat settings.ini`, `cooler.bin`, `reboot`)."
                ),
                "command": command,
                "required_bootstrap_command": None,
            }

        allowed, reason, bootstrap_command = self.policy.validate(command)
        if not allowed:
            return {
                "ok": False,
                "blocked": True,
                "reason": reason,
                "command": command,
                "required_bootstrap_command": bootstrap_command,
            }

        normalized_command = command.strip().replace("\\", "/")
        if normalized_command.startswith("cat ") and normalized_command.endswith("/.gitignore"):
            gitignore_target = normalized_command[4:].strip()
            base_dir = gitignore_target.rsplit("/", 1)[0] or "/"
            self.policy.mark_gitignore_checked(base_dir)

        shell_result = self.shell_api.run_command(command)
        if not shell_result.get("ok", False):
            result = {
                "ok": False,
                "blocked": False,
                "command": command,
                "error": shell_result.get("error_message"),
                "http_status": shell_result.get("http_status"),
                "is_retryable": shell_result.get("is_retryable"),
                "error_code": shell_result.get("error_code"),
                "ban": shell_result.get("ban"),
                "is_ban": shell_result.get("is_ban", False),
            }
            if self.settings.stop_on_ban and result.get("is_ban"):
                result["stop_agent"] = True
                result["stop_reason"] = "Wykryto ban w VM. Sesja została zatrzymana."
            return result

        response = shell_result.get("response", {})
        self._maybe_update_gitignore(command, response)
        self._update_task_signals(command=command, response=response)
        code = self._extract_eccs_code(response)
        return {
            "ok": True,
            "blocked": False,
            "command": command,
            "response": response,
            "detected_confirmation_code": code,
        }

    def _is_execution_mode_command_allowed(self, command: str) -> bool:
        """Sprawdza, czy komenda jest dozwolona w trybie finalizacji zadania.

        Args:
            command: Komenda shell proponowana przez model.

        Returns:
            `True`, gdy komenda jest zgodna z dozwolonym zestawem.
        """

        normalized = command.strip().replace("\\", "/")
        if normalized == "reboot":
            return True
        if normalized == "rm /opt/firmware/cooler/cooler-is-blocked.lock":
            return True
        if normalized == "cat /opt/firmware/cooler/settings.ini":
            return True
        if normalized.startswith("editline /opt/firmware/cooler/settings.ini "):
            return True
        if normalized == "/opt/firmware/cooler/cooler.bin":
            return True
        if normalized.startswith("/opt/firmware/cooler/cooler.bin "):
            return True
        return False

    def _update_task_signals(self, command: str, response: dict[str, Any]) -> None:
        """Aktualizuje sygnały postępu i aktywuje tryb finalizacji, gdy to możliwe.

        Args:
            command: Wykonana komenda shell.
            response: Odpowiedź shell API.
        """

        response_text = "\n".join(_extract_strings(response))
        if "admin1" in response_text:
            self.knows_admin_password = True
            self.admin_password = "admin1"

        normalized_command = command.strip().replace("\\", "/")
        response_path = str(response.get("path", "")).replace("\\", "/")
        if (
            normalized_command == "cat /opt/firmware/cooler/settings.ini"
            and response_path == "/opt/firmware/cooler/settings.ini"
        ):
            self.knows_settings_content = True
            data = response.get("data")
            if isinstance(data, str):
                self.settings_ini_content = data

        if (
            self.knows_admin_password
            and self.knows_settings_content
            and not self.execution_mode
        ):
            self.execution_mode = True
            self._record_event(
                {
                    "type": "execution_mode_enabled",
                    "reason": "Wykryto admin1 oraz odczyt settings.ini",
                }
            )
            log_terminal("Włączono execution mode: finalizacja zadania.")

    def _next_forced_command(self) -> str | None:
        """Wyznacza następny deterministyczny krok misji.

        Returns:
            Komenda do wymuszonego wykonania lub `None`, gdy brak kroku wymuszonego.
        """

        if self.knows_settings_content and not self.knows_admin_password:
            if not self.forced_attempted_pass_file:
                return "cat /home/operator/notes/pass.txt"
            if not self.forced_attempted_history:
                return "cat /home/operator/.bash_history"
            return None

        if self.execution_mode:
            if not self.forced_attempted_remove_lock:
                return "rm /opt/firmware/cooler/cooler-is-blocked.lock"

            content = self.settings_ini_content or ""
            if "[test_mode]" in content and "enabled=true" in content and not self.forced_attempted_disable_test_mode:
                return "editline /opt/firmware/cooler/settings.ini 6 enabled=false"

            if "[cooling]" in content and "enabled=false" in content and not self.forced_attempted_set_cooling_enabled:
                return "editline /opt/firmware/cooler/settings.ini 10 enabled=true"

            if not self.forced_attempted_run_with_password and self.admin_password:
                return f"/opt/firmware/cooler/cooler.bin {self.admin_password}"
            if not self.forced_attempted_run_without_password:
                return "/opt/firmware/cooler/cooler.bin"

        return None

    def _register_forced_command(self, command: str) -> None:
        """Oznacza wymuszoną komendę jako wykonaną próbę.

        Args:
            command: Komenda, która została wykonana.
        """

        normalized = command.strip().replace("\\", "/")
        if normalized == "cat /home/operator/notes/pass.txt":
            self.forced_attempted_pass_file = True
        elif normalized == "cat /home/operator/.bash_history":
            self.forced_attempted_history = True
        elif normalized == "rm /opt/firmware/cooler/cooler-is-blocked.lock":
            self.forced_attempted_remove_lock = True
        elif normalized == "editline /opt/firmware/cooler/settings.ini 6 enabled=false":
            self.forced_attempted_disable_test_mode = True
        elif normalized == "editline /opt/firmware/cooler/settings.ini 10 enabled=true":
            self.forced_attempted_set_cooling_enabled = True
        elif normalized.startswith("/opt/firmware/cooler/cooler.bin "):
            self.forced_attempted_run_with_password = True
        elif normalized == "/opt/firmware/cooler/cooler.bin":
            self.forced_attempted_run_without_password = True

    def _handle_submit_tool(self, confirmation: str) -> dict[str, Any]:
        """Wykonuje narzędzie `submit_answer`.

        Args:
            confirmation: Kod w formacie `ECCS-...`.

        Returns:
            Wynik wysyłki do endpointu verify.
        """

        if not ECCS_PATTERN.fullmatch(confirmation):
            return {
                "ok": False,
                "error": "Niepoprawny format kodu confirmation. Oczekiwano ECCS-...",
                "confirmation": confirmation,
            }
        response = self.verify_api.submit_confirmation(confirmation)
        return {"ok": True, "confirmation": confirmation, "response": response}

    def _execute_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Obsługuje pojedyncze wywołanie narzędzia zwrócone przez model.

        Args:
            tool_call: Struktura pojedynczego `tool_call` z odpowiedzi modelu.

        Returns:
            Ustandaryzowany wynik działania narzędzia.
        """

        function_data = tool_call.get("function", {})
        function_name = function_data.get("name", "")
        arguments = _safe_json_loads(function_data.get("arguments", "{}"))

        if function_name == "shell":
            command = str(arguments.get("command", "")).strip()
            return self._handle_shell_tool(command=command)
        if function_name == "submit_answer":
            confirmation = str(arguments.get("confirmation", "")).strip()
            return self._handle_submit_tool(confirmation=confirmation)
        return {"ok": False, "error": f"Nieznane narzędzie: {function_name}"}

    def _initialize_conversation(self) -> None:
        """Inicjalizuje wiadomości systemowe i cel zadania."""

        system_prompt = self._load_system_prompt()
        self.messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Rozwiąż zadanie firmware przez shell API. "
                    "Najpierw użyj komendy help. "
                    "Gdy uzyskasz kod ECCS, użyj submit_answer."
                ),
            },
        ]

    def _trim_messages(self) -> None:
        """Przycina historię wiadomości do ustalonego budżetu.

        Efekty uboczne:
            Modyfikuje `self.messages`, pozostawiając tylko najnowszy fragment rozmowy.
        """

        header_count = 2
        if len(self.messages) <= header_count + self.settings.max_history_messages:
            return
        preserved_head = self.messages[:header_count]
        preserved_tail = self.messages[-self.settings.max_history_messages :]
        self.messages = preserved_head + preserved_tail

    def _build_tool_message_content(self, result: dict[str, Any]) -> str:
        """Buduje skróconą treść wyniku narzędzia dla modelu.

        Args:
            result: Pełny wynik narzędzia.

        Returns:
            Skompresowany JSON w formie tekstowej.
        """

        compact: dict[str, Any] = {
            "ok": result.get("ok"),
            "blocked": result.get("blocked"),
            "command": result.get("command"),
            "http_status": result.get("http_status"),
            "error_code": result.get("error_code"),
            "is_ban": result.get("is_ban"),
            "required_bootstrap_command": result.get("required_bootstrap_command"),
            "detected_confirmation_code": result.get("detected_confirmation_code"),
            "stop_agent": result.get("stop_agent"),
            "stop_reason": result.get("stop_reason"),
            "execution_mode": self.execution_mode,
            "knows_admin_password": self.knows_admin_password,
            "knows_settings_content": self.knows_settings_content,
        }

        response = result.get("response")
        if isinstance(response, dict):
            compact["response_code"] = response.get("code")
            compact["response_message"] = response.get("message")
            compact["response_path"] = response.get("path")
            response_data = response.get("data")
            if isinstance(response_data, list):
                compact["response_data_preview"] = response_data[:8]
            elif isinstance(response_data, str):
                compact["response_data_preview"] = _truncate_text(
                    response_data,
                    max(200, self.settings.max_tool_message_chars // 3),
                )

        if result.get("error"):
            compact["error_preview"] = _truncate_text(
                str(result["error"]),
                max(250, self.settings.max_tool_message_chars // 2),
            )

        encoded = json.dumps(compact, ensure_ascii=False)
        return _truncate_text(encoded, self.settings.max_tool_message_chars)

    def run(self) -> dict[str, Any]:
        """Uruchamia pełną pętlę agentową do uzyskania i wysłania kodu.

        Returns:
            Słownik podsumowujący rezultat sesji.

        Efekty uboczne:
            Zapisuje pliki w `output`, wykonuje żądania HTTP do API shell/verify/OpenRouter.
        """

        self._initialize_conversation()
        tools = self._build_tools()
        submitted_code: str | None = None
        final_verify_response: dict[str, Any] | None = None
        stopped_due_to_ban = False
        stop_reason: str | None = None
        ban_details: dict[str, Any] | None = None
        used_steps = 0

        for step in range(1, self.settings.max_steps + 1):
            used_steps = step
            self._trim_messages()
            forced_command = self._next_forced_command()
            if forced_command:
                log_terminal(f"Krok {step}/{self.settings.max_steps}: wymuszona komenda misji.")
                self._register_forced_command(forced_command)
                forced_tool_call_id = f"forced-{step}-1"

                self.messages.append(
                    {
                        "role": "assistant",
                        "content": "Wykonuję wymuszoną komendę misji.",
                        "tool_calls": [
                            {
                                "id": forced_tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": "shell",
                                    "arguments": json.dumps(
                                        {"command": forced_command},
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ],
                    }
                )

                result = self._handle_shell_tool(forced_command)
                write_json(
                    self.output_dir / f"step{step:02d}_tool01_shell.json",
                    result,
                )
                self._record_event(
                    {
                        "type": "forced_tool_result",
                        "step": step,
                        "tool_name": "shell",
                        "payload": result,
                    }
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": forced_tool_call_id,
                        "name": "shell",
                        "content": self._build_tool_message_content(result),
                    }
                )

                detected_code = self._extract_eccs_code(result)
                if detected_code:
                    submitted_code = detected_code
                    final_verify_response = self.verify_api.submit_confirmation(detected_code)
                    break
                if result.get("stop_agent"):
                    stopped_due_to_ban = True
                    stop_reason = str(result.get("stop_reason", "Zatrzymano sesję."))
                    ban_details = {
                        "command": result.get("command"),
                        "http_status": result.get("http_status"),
                        "error_code": result.get("error_code"),
                        "ban": result.get("ban"),
                        "error": result.get("error"),
                    }
                    log_terminal("Wykryto ban VM. Kończenie sesji zgodnie z STOP_ON_BAN.")
                    break
                continue

            log_terminal(f"Krok {step}/{self.settings.max_steps}: zapytanie modelu.")
            model_response = self.openrouter.create_chat_completion(
                messages=self.messages,
                tools=tools,
            )

            write_json(self.output_dir / f"step{step:02d}_model_response.json", model_response)
            self._record_event({"type": "model_response", "step": step, "payload": model_response})

            choice = (model_response.get("choices") or [{}])[0]
            assistant_message = choice.get("message", {})
            assistant_content = assistant_message.get("content")
            tool_calls = assistant_message.get("tool_calls") or []

            self.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content or "",
                    "tool_calls": tool_calls,
                }
            )

            if not tool_calls:
                detected = self._extract_eccs_code(assistant_message)
                if detected:
                    submitted_code = detected
                    final_verify_response = self.verify_api.submit_confirmation(detected)
                    break
                continue

            ignored_tool_calls = max(0, len(tool_calls) - 1)
            if ignored_tool_calls > 0:
                log_terminal(
                    f"Krok {step}: odrzucono nadmiarowe tool_calls: {ignored_tool_calls}"
                )
                self._record_event(
                    {
                        "type": "ignored_tool_calls",
                        "step": step,
                        "count": ignored_tool_calls,
                    }
                )
                write_json(
                    self.output_dir / f"step{step:02d}_ignored_tool_calls.json",
                    {"ignored_count": ignored_tool_calls, "tool_calls": tool_calls[1:]},
                )

            tool_call = tool_calls[0]
            function_name = tool_call.get("function", {}).get("name", "unknown")
            log_terminal(f"Krok {step}: narzędzie 1/1 -> {function_name}")
            result = self._execute_tool_call(tool_call)
            write_json(
                self.output_dir / f"step{step:02d}_tool01_{function_name}.json",
                result,
            )
            self._record_event(
                {
                    "type": "tool_result",
                    "step": step,
                    "tool_index": 1,
                    "tool_name": function_name,
                    "payload": result,
                }
            )

            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", f"{step}-1"),
                    "name": function_name,
                    "content": self._build_tool_message_content(result),
                }
            )

            detected_code = self._extract_eccs_code(result)
            if function_name == "submit_answer" and result.get("ok"):
                submitted_code = str(result.get("confirmation"))
                final_verify_response = result.get("response", {})
                break
            if result.get("stop_agent"):
                stopped_due_to_ban = True
                stop_reason = str(result.get("stop_reason", "Zatrzymano sesję."))
                ban_details = {
                    "command": result.get("command"),
                    "http_status": result.get("http_status"),
                    "error_code": result.get("error_code"),
                    "ban": result.get("ban"),
                    "error": result.get("error"),
                }
                log_terminal("Wykryto ban VM. Kończenie sesji zgodnie z STOP_ON_BAN.")
                break
            if detected_code:
                self._record_event(
                    {
                        "type": "detected_code",
                        "step": step,
                        "code": detected_code,
                    }
                )

            if submitted_code:
                break
            if stopped_due_to_ban:
                break

        success = bool(submitted_code and final_verify_response is not None)
        summary = {
            "success": success,
            "submitted_code": submitted_code,
            "final_verify_response": final_verify_response,
            "steps_used": used_steps,
            "stopped_due_to_ban": stopped_due_to_ban,
            "stop_reason": stop_reason,
            "ban_details": ban_details,
        }
        write_json(self.output_dir / "final_result.json", summary)
        write_text(self.output_dir / "final_result.txt", json.dumps(summary, ensure_ascii=False, indent=2))
        return summary
