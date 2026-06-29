# Policy Metrics

Mild fatigue is optional and is excluded from false positive / false negative main metrics. Missing files are counted as skipped_missing_file and excluded from the main denominator. VLM is not allowed to override high_level_care.

| strategy | evaluated | false_trigger | missed_care | invalid_false_trigger | expected_success | cooldown_suppressed | quality_suppressed | high_level_triggers | vlm_override |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single_threshold | 44 | 0 | 0 | 0 | 14/14 | 0 | 0 | 14 | 0 |
| threshold_plus_cooldown | 44 | 0 | 12 | 0 | 2/14 | 12 | 0 | 2 | 0 |
| quality_gate_plus_cooldown | 44 | 0 | 12 | 0 | 2/14 | 12 | 15 | 2 | 0 |
