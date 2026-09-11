# Okoeditor (Season4 Lesson 1)

Szkielet projektu do realizacji zadania `okoeditor` przez API `/verify`.

## Założenia

- Wszystkie zmiany w systemie OKO wykonujemy przez API.
- Konfiguracja jest ładowana z `.env` przez Pydantic.
- Integracja z modelem jest przygotowana pod OpenRouter.
- Wyniki pośrednie i końcowe zapisują się do katalogu `output`.

## Struktura

- `main.py` - punkt wejścia programu.
- `config.py` - konfiguracja aplikacji (`.env` + Pydantic).
- `clients/` - klienci HTTP (OKO API, OpenRouter).
- `services/` - logika wykonawcza kroków zadania.
- `agents/` - orkiestracja przebiegu.
- `models/` - modele danych Pydantic.
- `utils/` - logowanie i zapis artefaktów.
- `output/` - pliki wynikowe.

## Artefakty uruchomień

- Każde uruchomienie zapisuje wyniki do osobnego katalogu:
  - `output/YYYYMMDD_HHMMSS/`
- Dodatkowo `output/latest_run.txt` wskazuje ostatni run.

## Start

1. Uzupełnij `Season4/.env` wymaganymi wartościami (projekt czyta konfigurację z tego pliku).
3. Uruchom lokalnie:

```bash
python main.py
```
