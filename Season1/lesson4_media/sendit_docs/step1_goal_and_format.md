# Sendit: Punkt 1 (cel i format)

## Cel
Przygotować poprawnie wypełnioną deklarację transportu SPK i wysłać ją do endpointu /verify dla taska `sendit`.

## Wymagany format wyniku
Payload POST:
- `task`: `sendit`
- `answer.declaration`: pełny tekst deklaracji jako **jeden string**, z zachowaniem formatu 1:1 zgodnie ze wzorem.

## Kryteria akceptacji
- Wszystkie pola mają poprawne wartości merytoryczne.
- Układ dokumentu (kolejność, separatory, odstępy, nowe linie) jest zgodny ze wzorem.
- Brak dopisanych uwag specjalnych (pole ma pozostać puste / zgodnie z wymaganiami wzoru).
