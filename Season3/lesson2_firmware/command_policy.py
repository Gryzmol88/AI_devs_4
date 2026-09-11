"""Programistyczne reguły bezpieczeństwa dla komend shell API."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class CommandPolicy:
    """Waliduje komendy przed wysłaniem do shell API.

    Atrybuty:
        forbidden_paths: Ścieżki, których nie wolno dotykać.
        forbidden_tokens: Dodatkowe tokeny podnoszące ryzyko naruszeń.
    """

    forbidden_paths: tuple[str, ...] = ("/etc", "/root", "/proc")
    forbidden_tokens: tuple[str, ...] = (
        " rm ",
        " rm\n",
        " mv ",
        " chmod ",
        " chown ",
        "sudo ",
    )
    blocked_gitignore_entries: set[str] = field(default_factory=set)
    blocked_gitignore_globs: set[str] = field(default_factory=set)
    checked_gitignore_dirs: set[str] = field(default_factory=set)
    loaded_gitignore_roots: set[str] = field(default_factory=set)
    allowed_destructive_commands: tuple[str, ...] = (
        "rm /opt/firmware/cooler/cooler-is-blocked.lock",
    )

    def _normalize_path(self, path: str) -> str:
        """Normalizuje ścieżkę do jednolitej postaci Unix.

        Args:
            path: Ścieżka wejściowa.

        Returns:
            Znormalizowana ścieżka bez końcowego ukośnika.
        """

        normalized = path.replace("\\", "/").strip()
        if not normalized.startswith("/"):
            normalized = "/" + normalized.lstrip("/")
        return normalized.rstrip("/") or "/"

    def _extract_paths_from_command(self, command: str) -> list[str]:
        """Wydobywa ścieżki bezwzględne z komendy.

        Args:
            command: Komenda shell.

        Returns:
            Lista znormalizowanych ścieżek znalezionych w komendzie.
        """

        raw_paths = re.findall(r"/[A-Za-z0-9._/\-]*", command)
        return [self._normalize_path(item) for item in raw_paths if item]

    def update_blocked_entries(self, entries: list[str], base_dir: str) -> None:
        """Aktualizuje listę pozycji z `.gitignore` zakazanych do dotykania.

        Args:
            entries: Lista wpisów odczytanych z `.gitignore`.
            base_dir: Katalog, którego dotyczy odczytany `.gitignore`.
        """

        normalized_base = self._normalize_path(base_dir)
        self.loaded_gitignore_roots.add(normalized_base)
        self.checked_gitignore_dirs.add(normalized_base)

        for entry in entries:
            cleaned = entry.strip()
            if not cleaned or cleaned.startswith("#") or cleaned.startswith("!"):
                continue

            has_glob = "*" in cleaned or "?" in cleaned or "[" in cleaned
            normalized_entry = cleaned.replace("\\", "/")
            while normalized_entry.startswith("./"):
                normalized_entry = normalized_entry[2:]
            if normalized_entry == "":
                continue
            if normalized_entry.startswith("/"):
                absolute_entry = self._normalize_path(normalized_entry)
            else:
                absolute_entry = self._normalize_path(f"{normalized_base}/{normalized_entry}")

            if cleaned.endswith("/"):
                absolute_entry = absolute_entry + "/"

            if absolute_entry.endswith("/.gitignore") or absolute_entry == ".gitignore":
                continue

            if has_glob:
                self.blocked_gitignore_globs.add(absolute_entry)
            else:
                self.blocked_gitignore_entries.add(absolute_entry)

    def mark_gitignore_checked(self, directory: str) -> None:
        """Oznacza katalog jako sprawdzony pod kątem `.gitignore`.

        Args:
            directory: Katalog, dla którego wykonano próbę odczytu `.gitignore`.
        """

        self.checked_gitignore_dirs.add(self._normalize_path(directory))

    def _is_likely_file_path(self, command: str, path: str) -> bool:
        """Szacuje, czy ścieżka z komendy reprezentuje plik.

        Args:
            command: Pełna komenda shell.
            path: Znormalizowana ścieżka.

        Returns:
            `True`, gdy ścieżka najpewniej oznacza plik.
        """

        tokens = command.strip().split()
        verb = tokens[0] if tokens else ""
        if verb in {"cat", "sed", "head", "tail"}:
            return True
        basename = path.rsplit("/", 1)[-1]
        return "." in basename and verb not in {"ls", "cd", "find"}

    def _parent_dir(self, path: str) -> str:
        """Zwraca katalog nadrzędny dla wskazanej ścieżki.

        Args:
            path: Znormalizowana ścieżka.

        Returns:
            Ścieżka katalogu nadrzędnego.
        """

        if path == "/":
            return "/"
        parent = path.rsplit("/", 1)[0]
        return parent or "/"

    def _build_bootstrap_command(self, directory: str) -> str:
        """Buduje komendę bootstrapującą odczyt `.gitignore`.

        Args:
            directory: Katalog docelowy.

        Returns:
            Komenda `cat <directory>/.gitignore`.
        """

        normalized = self._normalize_path(directory)
        return f"cat {normalized}/.gitignore"

    def _path_depth(self, path: str) -> int:
        """Oblicza głębokość ścieżki bezwzględnej.

        Args:
            path: Znormalizowana ścieżka.

        Returns:
            Liczba segmentów ścieżki, np. `/a/b` -> 2.
        """

        normalized = self._normalize_path(path)
        if normalized == "/":
            return 0
        return len([segment for segment in normalized.split("/") if segment])

    def _requires_gitignore_bootstrap(self, command: str) -> tuple[bool, str, str | None]:
        """Sprawdza, czy wymagany jest wcześniejszy odczyt `.gitignore`.

        Args:
            command: Komenda do walidacji.

        Returns:
            Krotka `(czy_wymaga_blokady, powód, komenda_bootstrap)`.
        """

        normalized_command = command.strip().replace("\\", "/")
        paths = self._extract_paths_from_command(normalized_command)
        if not paths:
            return False, "", None

        for path in paths:
            if path.endswith("/.gitignore"):
                continue
            candidate_dir = path if not self._is_likely_file_path(normalized_command, path) else self._parent_dir(path)
            if "/.git" in candidate_dir:
                continue
            if self._path_depth(candidate_dir) <= 1:
                continue
            if self._is_path_blocked_by_gitignore(candidate_dir):
                continue
            if candidate_dir in self.checked_gitignore_dirs:
                continue
            bootstrap_command = self._build_bootstrap_command(candidate_dir)
            return (
                True,
                f"Najpierw odczytaj {candidate_dir}/.gitignore przed pracą w tym katalogu",
                bootstrap_command,
            )

        return False, "", None

    def _is_path_blocked_by_gitignore(self, path: str) -> bool:
        """Sprawdza, czy ścieżka jest już blokowana przez reguły `.gitignore`.

        Args:
            path: Znormalizowana ścieżka katalogu lub pliku.

        Returns:
            `True`, gdy ścieżka podpada pod aktualne reguły blokujące.
        """

        normalized_path = self._normalize_path(path)
        for blocked in self.blocked_gitignore_entries:
            blocked_path = blocked.rstrip("/")
            if normalized_path == blocked_path or normalized_path.startswith(f"{blocked_path}/"):
                return True
        for pattern in self.blocked_gitignore_globs:
            normalized_pattern = pattern.rstrip("/")
            if fnmatch.fnmatch(normalized_path, normalized_pattern):
                return True
        return False

    def validate(self, command: str) -> tuple[bool, str, str | None]:
        """Sprawdza, czy komenda jest zgodna z polityką bezpieczeństwa.

        Args:
            command: Komenda proponowana do wykonania.

        Returns:
            Krotka `(czy_poprawna, komunikat, komenda_bootstrap)`.
        """

        normalized = f" {command.strip()} "
        normalized_command = command.strip().replace("\\", "/")
        command_paths = self._extract_paths_from_command(command)

        for path in self.forbidden_paths:
            if path in command:
                return False, f"Komenda odwołuje się do zabronionej ścieżki: {path}", None

        requires_bootstrap, bootstrap_reason, bootstrap_command = self._requires_gitignore_bootstrap(command)
        if requires_bootstrap:
            return False, bootstrap_reason, bootstrap_command

        for token in self.forbidden_tokens:
            if token in normalized:
                if normalized_command in self.allowed_destructive_commands:
                    break
                return False, f"Komenda zawiera ryzykowną operację: {token.strip()}", None

        for blocked in self.blocked_gitignore_entries:
            blocked_path = blocked.rstrip("/")
            for path in command_paths:
                if path.endswith("/.gitignore"):
                    continue
                if path == blocked_path or path.startswith(f"{blocked_path}/"):
                    return False, f"Komenda dotyka wpisu z .gitignore: {blocked}", None

        for pattern in self.blocked_gitignore_globs:
            normalized_pattern = pattern.rstrip("/")
            for path in command_paths:
                if path.endswith("/.gitignore"):
                    continue
                if fnmatch.fnmatch(path, normalized_pattern):
                    return False, f"Komenda dotyka wzorca z .gitignore: {pattern}", None

        return True, "OK", None
