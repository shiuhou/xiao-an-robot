# E2E Smoke Checklist

Fake/mock smoke only. This table is not real robot execution evidence.

| scenario | expected | triggered | action_requested | cooldown | vlm_override | result | reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| normal_observe | no_trigger | False | False | False | False | pass | normal_observe did not trigger |
| fatigue_care | trigger | True | True | False | False | pass | fatigue_care triggered |
| low_quality_guard | no_trigger | False | False | False | False | pass | low_quality_guard: insufficient_evidence |
| cooldown_guard#1 | trigger | True | True | False | False | pass | first fatigue sample triggered |
| cooldown_guard#2 | cooldown | False | False | True | False | pass | second fatigue sample suppressed by cooldown |
| vlm_override_guard | no_trigger | False | False | False | False | pass | nested VLM high score did not override CV primary fields |
