# Quality Gate Stress Test

This is a policy stress test with injected strong fatigue/negative signals on invalid or low-reliability scenes. It is not real model output.

| strategy | stress_sample_count | high_level_trigger_count | suppressed_by_quality_count | suppressed_by_cooldown_count | invalid_false_trigger_count |
| --- | --- | --- | --- | --- | --- |
| single_threshold | 15 | 15 | 0 | 0 | 15 |
| threshold_plus_cooldown | 15 | 2 | 0 | 13 | 2 |
| quality_gate_plus_cooldown | 15 | 0 | 15 | 0 | 0 |
