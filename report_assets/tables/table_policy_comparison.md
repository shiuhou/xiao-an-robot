# Policy Comparison

These are policy-level counts from label-derived surrogate samples, not model prediction accuracy.

| scene | expected_behavior | single_threshold_high | threshold_cooldown_high | quality_gate_high | conclusion |
| --- | --- | --- | --- | --- | --- |
| normal_focus | observe only, no interruption | 0 | 0 | 0 | lower high count is better |
| normal_smile | observe only, no interruption | 0 | 0 | 0 | lower high count is better |
| bad_frame | reject or observe due to poor frame quality | 0 | 0 | 0 | lower high count is better |
| lowlight | reject or low-confidence observe | 0 | 0 | 0 | lower high count is better |
| no_face | no face, no care decision | 0 | 0 | 0 | lower high count is better |
| occlusion | no high-level care | 0 | 0 | 0 | lower high count is better |
| mild_fatigue | light hint or expression only | 0 | 0 | 0 | optional; excluded from main pass/fail metrics |
| severe_sleepy | care reminder expected | 5 | 0 | 0 | high-level care expected when not suppressed by cooldown |
| yawn | fatigue reminder expected | 4 | 1 | 1 | high-level care expected when not suppressed by cooldown |
| negative_affect | gentle care expected | 5 | 1 | 1 | high-level care expected when not suppressed by cooldown |
