# Punkty 5-7: Reguly, trasa i oplata

## Punkt 5: Reguly biznesowe
- Wzor deklaracji: `zalacznik-E.md`.
- Trasy do Zarnowca sa wylaczone; moga byc uzyte tylko dla kategorii A lub B (index.md sekcja 8.3).
- Oplata bazowa: A=0, B=0; C=2, D=5, E=10 (index.md sekcja 9.2).
- Zwolnienia: przesylki A i B sa zwolnione z oplat (index.md sekcja 9.4).
- Dodatkowe wagony: dla A i B nie nalicza sie oplaty za dodatkowe wagony (`dodatkowe-wagony.md`).
- WDP = Wagony Dodatkowe Platne (zalacznik-G.md).

## Punkt 6: Trasa i kod
- Start: Gdansk
- Cel: Zarnowiec
- Kod trasy: `X-01` (z `trasy-wylaczone.png`)

## Punkt 7: Oplata przy budzecie 0 PP
Dane:
- Masa: 2800 kg
- Kategoria dobrana: `A` (strategiczna) - zgodna z wymogiem przejazdu do Zarnowca i finansowania przez System.

Wyliczenie:
- OB = 0 PP
- OW = 0 PP (zwolnienie kat. A)
- OT = 0 PP (zwolnienie kat. A)
- Dodatkowe wagony: potrzebne technicznie, ale bez doplaty dla A

WDP:
- Standard: 1000 kg
- Nadmiar: 2800 - 1000 = 1800 kg
- Jeden wagon: 500 kg
- Potrzebne dodatkowe wagony: ceil(1800/500) = `4`

Wynik:
- `KWOTA DO ZAPLATY: 0 PP`
- `WDP: 4`
