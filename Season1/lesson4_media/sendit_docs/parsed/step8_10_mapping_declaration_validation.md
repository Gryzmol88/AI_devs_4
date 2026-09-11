# Punkty 8-10: Mapowanie danych, zlozenie deklaracji i walidacja lokalna

## Punkt 8: Mapowanie danych wejsciowych
- Nadawca -> `450202122`
- Punkt nadawczy -> `Gdansk`
- Punkt docelowy -> `Zarnowiec`
- Waga -> `2800`
- Budzet -> `0 PP`
- Zawartosc -> `kasety z paliwem do reaktora`
- Uwagi specjalne -> puste

## Punkt 9: Zlozony dokument
- Plik: `parsed/declaration_candidate.txt`
- Uklad zachowany wg wzoru z `zalacznik-E.md`

## Punkt 10: Walidacja lokalna
Checklist:
- [x] Wszystkie sekcje z wzoru obecne
- [x] Kolejnosc sekcji zgodna ze wzorem
- [x] Pole TRASA uzupelnione (`X-01`)
- [x] Pole KATEGORIA uzupelnione (`A`)
- [x] Masa uzupelniona (`2800`)
- [x] WDP uzupelnione (`4`)
- [x] Kwota zgodna z budzetem i reguami (`0 PP`)
- [x] Pole uwag pozostawione puste

Uwaga:
- Uzyto zapisu bez polskich znakow (ASCII), aby uniknac problemow kodowania widocznych w pobranych plikach.
- Finalna wysylka do `/verify` nie zostala wykonana (to jest punkt 11).
