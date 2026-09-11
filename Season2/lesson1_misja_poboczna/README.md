# lesson1_misja_poboczna

Narzędzie do misji pobocznej dla S02E01.

Zakłada, że masz zaliczone elementy `A..J` i chcesz ułożyć je wg podpowiedzi:

`J-D-I-B-A-C-G-E-H-F`

Domyślnie skrypt jest powiązany z `Season2/lesson1_kontekst` i bez argumentów:
- czyta `Season2/lesson1_kontekst/output/api_trace.jsonl`,
- bierze ostatnie pełne podejście (10x `VERIFY_ITEM`),
- próbuje mapować po markerach promptu `L:A..J`,
- jeśli markerów brak, mapuje `A..J` wg kolejności zaliczeń,
- stosuje hint `J-D-I-B-A-C-G-E-H-F`.

## Uruchomienie

### Opcja 0: Automatycznie z logów lesson1_kontekst

```powershell
python Season2\lesson1_misja_poboczna\main.py
```

Domyślnie bierze `value-source=id` (identyfikatory towarów z `VERIFY_ITEM_*_ID_*`).

Możesz zmienić źródło wartości:

```powershell
python Season2\lesson1_misja_poboczna\main.py --value-source output
```

Dostępne: `id`, `output`, `message`, `status_code`.

### Opcja 0b: Automatycznie + wysyłka do centrali (zalecane)

```powershell
python Season2\lesson1_misja_poboczna\main.py --submit --submit-mode replay_order
```

Skrypt:
- buduje sekwencję powiązaną z `lesson1_kontekst`,
- wysyła `reset`,
- wysyła 10 promptów klasyfikacyjnych (`answer.prompt`) w kolejności `J-D-I-B-A-C-G-E-H-F`,
- zatrzymuje się na pierwszym `{FLG:...}`.
- używa domyślnie własnego, wzmocnionego promptu klasyfikacyjnego.

Możesz wymusić task lub endpoint:

```powershell
python Season2\lesson1_misja_poboczna\main.py --submit --submit-mode replay_order --task categorize --verify-url https://hub.ag3nts.org/verify
```

Jeśli chcesz użyć template z zadania głównego:

```powershell
python Season2\lesson1_misja_poboczna\main.py --submit --submit-mode replay_order --prompt-template-file Season2\lesson1_kontekst\output\current_prompt.json
```

### Opcja 1: Podaj 10 wartości bezpośrednio (kolejność A..J)

```powershell
python Season2\lesson1_misja_poboczna\main.py --values A_VAL B_VAL C_VAL D_VAL E_VAL F_VAL G_VAL H_VAL I_VAL J_VAL
```

### Opcja 2: JSON z mapą

Przykład pliku:

```json
{
  "A": "A_VAL",
  "B": "B_VAL",
  "C": "C_VAL",
  "D": "D_VAL",
  "E": "E_VAL",
  "F": "F_VAL",
  "G": "G_VAL",
  "H": "H_VAL",
  "I": "I_VAL",
  "J": "J_VAL"
}
```

Uruchomienie:

```powershell
python Season2\lesson1_misja_poboczna\main.py --input-json Season2\lesson1_misja_poboczna\answers.json
```

### Opcja 3: TXT z mapą `KEY=VALUE`

Przykład:

```text
A=A_VAL
B=B_VAL
C=C_VAL
D=D_VAL
E=E_VAL
F=F_VAL
G=G_VAL
H=H_VAL
I=I_VAL
J=J_VAL
```

Uruchomienie:

```powershell
python Season2\lesson1_misja_poboczna\main.py --input-text Season2\lesson1_misja_poboczna\answers.txt
```

## Wynik

Skrypt zapisuje wynik do:

- `Season2/lesson1_misja_poboczna/output/result.json`

W trybie automatycznym dopisuje też `trace_meta`:
- ścieżkę logu,
- numer wybranego podejścia,
- `mapping_mode` (`prompt_labels` albo `verify_order`),
- wykryte ewentualne znaczniki literowe `A..J` w odpowiedziach huba.

Przy `--submit` zapisuje dodatkowo:
- `output/submit_trace.jsonl` (wszystkie requesty/response do centrali),
- sekcję `submit` w `output/result.json`.
