# Project Status - 2026-06-28

This file records the 2026-06-28 DK2500/OpenClaw integration status after the 2026-06-27 full hardware handoff. It should be read together with `docs/project_status_2026-06-27.md`.

## Summary

Status reported on 2026-06-28:

- Base-station/OpenClaw can control the robot through `/control`.
- Base-station/OpenClaw can receive robot camera data through `/video`.
- Base-station/OpenClaw can receive robot microphone data through `/audio`.
- OpenClaw can inspect the current `runtime/latest.jpg` camera frame and provide feedback about the image content.

This moves the project from "robot hardware channels are locally verified" to "DK2500/OpenClaw can consume and act on the robot's live IO channels".

## Completed

| Area | Status | Evidence |
| --- | --- | --- |
| `/control` robot command path | PASS_H | OpenClaw/base path can control the robot |
| `/video` robot camera path | PASS_H/P | Robot camera frame reaches base station as `runtime/latest.jpg`; OpenClaw can inspect the image content and respond |
| `/audio` robot microphone path | PASS_H/P | Robot audio stream reaches the base station/OpenClaw side |
| OpenClaw image feedback | PASS_P/H | OpenClaw reads the latest robot camera frame and produces content feedback |

Notes:

- `PASS_H/P` means the data originates from real robot hardware, while part of the interpretation or reporting is software-side.
- This record does not claim real spoken TTS output. The known reliable audible path remains `audio.play_local care_01`; `audio.play_tts` is still a mock tone unless replaced by a real TTS path.
- This record does not claim full autonomous policy quality. It confirms channel reachability and OpenClaw image understanding over the live robot frame.

## Current Baseline

Firmware and channel baseline from 2026-06-27 remains active:

- Firmware target: `mergetesting_full_face240`.
- Robot command route: `/control`.
- Camera route: `/video` -> `runtime/latest.jpg`.
- Audio route: `/audio` -> base-station PCM/runtime artifacts.
- Practical floor motion setting: `speed=0.56` for dock-exit demo motion.
- Minimum effective positive speed: `0.52`.

## Protocol/Status Documentation Alignment

`docs/protocol.md` was updated on 2026-06-28 before main-branch merge preparation. It now reflects the live `/control`, `/audio`, and `/video` implementation state instead of the older draft status. The protocol document now points to the 2026-06-26/27/28 status records, the mergetesting registry, and the priority queue results as evidence for the current H/P state.

Current protocol truth:

- `/control` is the live robot command path.
- `/video` is the live robot camera path and updates `runtime/latest.jpg`.
- `/audio` is the live robot microphone PCM path to the base-station/OpenClaw side.
- `mergetesting_full_face240` is the current full firmware baseline for face240 + motor + speaker + `/video` + `/audio`.
- Real spoken TTS remains separate future work; the reliable audible cue is still `audio.play_local care_01`.

## What This Unblocks

The next meaningful milestone is no longer isolated channel testing. The next milestone is an end-to-end closed-loop behavior:

```text
robot camera/audio -> base station/OpenClaw perception -> action decision
  -> /control command -> robot movement/expression/sound
  -> matching ack/completed/log evidence
```

## Recommended Next Steps

Detailed execution plan: `docs/superpowers/plans/2026-06-28-dk2500-openclaw-care-loop.md`.

1. **Lock a reproducible DK2500 smoke script.**
   - One command should verify `/control`, `/video`, `/audio`, `latest.jpg` inspection, and one safe robot action.
   - The script should save only short summaries, not large logs/images/audio in Git.

2. **Verify action completion semantics from OpenClaw.**
   - For every motion action, confirm `command.ack` and matching `motion.completed` with the same `action_id`.
   - Do this before chaining multiple movement actions in an autonomous demo.

3. **Build the first autonomous care loop.**
   - Use the latest camera frame or a scripted tired/emotion trigger.
   - Expected action sequence: expression change, short dock-exit motion, optional turn-to-user, and audible response.
   - Keep speed at `0.56`, with explicit duration/timeout and a stop fallback.

4. **Replace mock TTS with a real spoken path, or label it clearly as mock.**
   - Current reliable sound proof: `audio.play_local care_01`.
   - Real spoken output needs a defined base-station TTS -> robot speaker path.

5. **Add regression tests for the DK2500/OpenClaw bridge.**
   - Unit tests for command payload shape.
   - Integration smoke for image-frame feedback using `runtime/latest.jpg`.
   - Event wait test for `motion.completed`.

6. **Calibrate the physical demo route.**
   - Measure dock exit and turn durations on charged battery.
   - Keep a small table for distance/time/speed, starting with `speed=0.56`.

## Suggested Next Demo Contract

Use this as the next target behavior:

```text
When OpenClaw sees a person or receives a tired/care trigger:
1. Set expression to caring or happy.
2. Move forward out of base with speed=0.56, duration_ms=2000.
3. Wait for matching motion.completed.
4. Turn left/right toward the user with speed=0.56, duration_ms=500.
5. Wait for matching motion.completed.
6. Play local care_01 or real TTS if implemented.
7. Log the camera-frame observation that caused the action.
```

## Open Questions

- Does the OpenClaw side currently receive `motion.completed` consistently after each motion command?
- Is `/audio` currently only captured as PCM, or has it been connected to real ASR?
- Should the next public demo use `audio.play_local care_01` for reliability, or wait for real spoken TTS?
- Which branch should be the integration source of truth after 2026-06-28: `mergetestint_robot` or `integration/openclaw-mergetesting-fusion`?
