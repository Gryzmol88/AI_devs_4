# lesson1_evaluation

Rozwiązanie do zadania `evaluation` z lekcji S03E01.

## Co robi pipeline

1. Wczytuje pliki sensorów.
2. Wykrywa anomalie regułami deterministycznymi.
3. Klasyfikuje `operator_notes` (heurystyka + OpenRouter dla przypadków niejednoznacznych).
4. Łączy anomalie i tworzy `recheck`.
5. Zapisuje wyniki pośrednie i końcowe do `output/`.
6. Opcjonalnie liczy raport ewaluacyjny (`eval_report.json`) i wysyła payload do `/verify`.

## Pliki wyjściowe (output)

- `step1_rules_anomalies.json`
- `step2_notes_assessments.json`
- `step2_note_consistency_anomalies.json`
- `step3_merged_recheck.json`
- `step3_reason_index.json`
- `final_payload.json`
- `final_result.txt`
- `eval_report.json` (jeśli podasz `--gold-path`)
- `eval_summary.txt` (jeśli podasz `--gold-path`)
- `verify_response.json` (jeśli podasz `--verify`)

## Format gold labels

Patrz: `schemas/gold_labels.example.json`

```json
{
  "labels": [
    {
      "file_id": "0001",
      "expected_recheck": true,
      "expected_rule_anomaly": true,
      "expected_note_stance": "ok"
    }
  ]
}
```

## Format notes gold

Patrz: `schemas/notes_gold.example.json`

```json
{
  "labels": [
    {
      "note": "Readings look stable and within expected range.",
      "expected_stance": "ok"
    }
  ]
}
```

## Format eval_report.json

```json
{
  "thresholds": {
    "precision_min": 0.995,
    "recall_min": 0.999,
    "f1_min": 0.99,
    "notes_accuracy_min": 0.97,
    "llm_usage_ratio_max": 0.05,
    "runtime_seconds_max": 120.0
  },
  "metrics": {
    "rules_precision": 1.0,
    "rules_recall": 1.0,
    "recheck_f1": 1.0,
    "notes_accuracy": 1.0,
    "llm_usage_ratio": 0.01,
    "runtime_seconds": 45.3
  },
  "pass_all": true,
  "sample_count": 200,
  "notes": [
    "If rules_expected is missing, rules precision/recall fallback to end-to-end recheck stats.",
    "notes_accuracy should be measured on a labeled subset of operator_notes."
  ]
}
```

## Przykładowe uruchomienie

```bash
python main.py --download --extract
python main.py --gold-path schemas/gold_labels.example.json --notes-gold-path schemas/notes_gold.example.json
python main.py --verify
```

