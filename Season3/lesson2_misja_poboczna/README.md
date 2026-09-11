# lesson2_misja_poboczna

Rozwiazanie pobocznej misji oparte o fundamenty z `lesson2_firmware`.

Hint misji: `Uruchom mnie z niemieckim motylem`.

## Najwazniejsze zalozenia

- Runner jest deterministyczny (bez petli LLM), wiec zuzycie tokenow jest minimalne.
- Konfiguracja jest typowana przez Pydantic i ladowana z `Season3/.env`.
- Polityka bezpieczenstwa respektuje `.gitignore` dynamicznie dla odwiedzanych katalogow.
- Kazdy run zapisuje komplet artefaktow do osobnego `output/session_*`.

## Jak dziala

1. Wykonuje komendy wstepne (`SIDE_TASK_PRE_COMMANDS`), domyslnie:
   - rekonesans katalogow,
   - przeglad katalogu firmware (`ls /opt`, `ls /opt/firmware`, `ls /opt/firmware/cooler`),
   - `cat /home/operator/notes/pass.txt`,
   - `cat /home/operator/.bash_history`.
2. Z odpowiedzi shell API wyciaga kandydatow hasla tylko z komend `cat`:
   - `pass.txt` jako priorytet `HIGH`,
   - `.bash_history` jako priorytet `MEDIUM`.
3. Buduje probe uruchomienia binarki:
   - najpierw kandydaci wykryci dynamicznie,
   - potem ograniczona lista kandydatow z hintu (`Schmetterling` i "wihajster"-like).
4. Gdy binarka zwroci komunikat o lockfile, runner:
   - usuwa lock (`rm /opt/firmware/cooler/cooler-is-blocked.lock`),
   - ponawia ostatnia komende.
5. Po kazdym kroku wykrywa kod sukcesu regexem `SIDE_TASK_SUCCESS_REGEX`.
6. Po sukcesie zapisuje wynik i opcjonalnie wysyla odpowiedz na `/verify`.

## Kluczowe pliki

- `main.py` - punkt wejscia.
- `agent_loop.py` - glowny runner i logika wykrywania kandydatow.
- `hints.py` - lista kandydatow wynikajacych z podpowiedzi.
- `config.py` - ustawienia `.env` przez Pydantic.
- `command_policy.py` - walidacja komend i obsluga `.gitignore`.

## Konfiguracja

Minimalne pola w `Season3/.env`:

- `HUB_API_KEY`
- `SIDE_TASK_NAME` (domyslnie `lesson2_side`)
- `SIDE_TASK_BINARY_PATH` (domyslnie `/opt/firmware/cooler/cooler.bin`)
- `SIDE_TASK_ANSWER_KEY` (domyslnie `confirmation`)
- `SIDE_TASK_SUCCESS_REGEX` (domyslnie `ECCS-[A-Za-z0-9]{40}`)

Przydatne:

- `SIDE_TASK_PRE_COMMANDS` - lista komend wstepnych rozdzielona przecinkami.
- `STOP_ON_BAN` - czy przerywac sesje przy banie VM.
- `CAPTURE_FILE_CONTENTS` - czy zapisywac tresci napotkanych plikow.
- `CAPTURE_MAX_FILES` - limit liczby plikow do odczytu.
- `CAPTURE_MAX_CHARS` - limit znakow zapisu na plik.
- `DISCOVER_FULL_FS` - czy skanowac caly filesystem (z pominieciem zabronionych sciezek).
- `DISCOVER_MAX_DIRS` - limit katalogow dla skanu BFS.

## Uruchomienie

```powershell
python .\Season3\lesson2_misja_poboczna\main.py
```

Probe samego `/bin/flaggengenerator`:

```powershell
python .\Season3\lesson2_misja_poboczna\flaggengenerator_probe.py
```

## Artefakty output

Kazdy run zapisuje:

- `output/session_YYYYMMDDTHHMMSSZ_<id>/session_log.jsonl`
- `stepXX_tool01_shell.json` (+ ewentualnie `_bootstrap` i `_retry`)
- `paths_seen.json` (lista wszystkich napotkanych sciezek + podzial na katalogi i pliki)
- `paths_tree.txt` (drzewo odtworzone ze sciezek)
- `filesystem_discovery.json` (statystyki skanowania calego FS)
- `files_content_index.json` (indeks prob odczytu tresci plikow)
- `files_content/*.json` (zrzuty tresci napotkanych plikow)
- `final_result.json` i `final_result.txt`
- `fatal_error.json` przy bledzie krytycznym
