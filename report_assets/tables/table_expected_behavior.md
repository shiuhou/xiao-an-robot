# Expected Behavior

| scene | expected_behavior | expected_trigger | rationale |
| --- | --- | --- | --- |
| normal_focus | observe only, no interruption | false | normal focused state |
| normal_smile | observe only, no interruption | false | positive/normal state |
| bad_frame | reject or observe due to poor frame quality | false | unreliable visual evidence |
| lowlight | reject or low-confidence observe | false | insufficient lighting |
| no_face | no face, no care decision | false | no valid human face |
| occlusion | no high-level care | false | face is occluded |
| mild_fatigue | light hint or expression only | optional | weak fatigue evidence |
| severe_sleepy | care reminder expected | true | strong fatigue evidence |
| yawn | fatigue reminder expected | true | yawn evidence |
| negative_affect | gentle care expected | true | negative affect evidence |
