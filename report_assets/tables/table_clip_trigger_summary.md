# Clip Trigger Summary

These timelines use label-derived clip timeline samples, not model predictions.

| clip_id | clip_type | expected | first_trigger_s | high_level_triggers | expression_only | cooldown_suppressed | quality_suppressed | result | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| s01_bad_quality_clip_0001 | bad_quality | false |  | 0 | 0 | 0 | 10 | pass | no high-level care triggered |
| s01_clip_blink_normal_0001 | blink | false |  | 0 | 0 | 0 | 0 | pass | no high-level care triggered |
| s01_clip_eyes_closed_long_0001 | eyes_closed_long | true | 1.0 | 1 | 0 | 9 | 0 | pass | expected high-level care triggered |
| s01_clip_head_down_sleepy_0001 | head_down_sleepy | true | 1.0 | 1 | 0 | 7 | 0 | pass | expected high-level care triggered |
| s01_clip_no_face_clip_0001 | no_face | false |  | 0 | 0 | 0 | 10 | pass | no high-level care triggered |
| s01_clip_normal_working_0001 | normal_working | false |  | 0 | 0 | 0 | 0 | pass | no high-level care triggered |
| s01_clip_yawn_clip_0001 | yawn | true | 1.0 | 1 | 0 | 9 | 0 | pass | expected high-level care triggered |
| s01_eyes_closed_short_0001 | eyes_closed_short | optional |  | 0 | 10 | 0 | 0 | pass | optional clip handled as expression_only |
