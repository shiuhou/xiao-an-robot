# DK2500 OpenClaw Care Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current working `/control`, `/video`, and `/audio` channels into a reproducible DK2500/OpenClaw care demo with reliable command completion evidence.

**Architecture:** Keep the robot firmware in `robot/mergetesting` stable and treat DK2500/OpenClaw as the orchestration side. First add a repeatable smoke script, then harden `motion.completed` propagation through `/agent`, then use the hardened path for the first autonomous care loop. Real spoken TTS is lower priority than a reliable closed loop; keep `audio.play_local care_01` as the demo-safe sound until real TTS is explicitly implemented.

**Tech Stack:** Python `unittest`, `websockets`, `base_station.ws_server`, `agent.core.RobotGateway`, `agent.skills.RobotMotionSkill`, ESP32-S3 `mergetesting_full_face240`, WebSocket `/control` `/video` `/audio` `/agent`.

## Global Constraints

- Do not commit `robot/mergetesting/src/config.local.h`, runtime images/audio/logs, databases, `.pio/`, venvs, or secrets.
- DK2500/base-station integration behavior belongs in `robot/mergetesting`, `base_station`, `agent`, `tools`, `tests`, and `docs`; do not move the integration entrypoint into `robot/firmware/src/main.cpp`.
- Keep the current motor safety envelope: minimum effective positive speed `0.52`, demo forward speed `0.56`, dock-exit duration `2000ms`, left/right turn duration about `500ms`.
- Hardware PASS_H requires robot logs, base-station logs, generated runtime evidence, or user physical observation. Do not mark H from software assumptions alone.
- For every movement in an autonomous sequence, require `command.ack` plus matching `motion.completed` for the same `action_id` before issuing the next movement.
- Use `audio.play_local care_01` for reliable sound demos until real spoken TTS is implemented and tested.
- Run focused tests after each task; run full `python -m unittest discover -s tests -p "test_*.py"` before publish.

---

## File Structure

- Create `tools/run_dk2500_openclaw_smoke.py`: one-command DK2500 smoke script for channel checks, latest frame/audio artifact checks, image-feedback check hook, and one safe action.
- Create `tests/unit/test_dk2500_openclaw_smoke.py`: unit tests for smoke-script command construction and artifact checks.
- Modify `base_station/ws_server/server.py`: propagate `motion.completed` from `/control` back to `/agent` clients that requested completion wait.
- Modify `tests/integration/test_ws_command_forwarding.py`: integration test for `/agent` receiving both `agent.ack` and `agent.motion_completed`.
- Modify `agent/core/gateway.py`: allow motion commands to request completion wait and return both ack and completion.
- Modify `agent/skills/robot_motion.py`: make care actions sequence on completion when requested.
- Modify `tests/unit/test_robot_motion_skill.py` and `tests/integration/test_robot_motion_skill.py`: cover safe speed, completion-aware sequencing, and local-sound fallback.
- Create `tools/run_openclaw_care_demo.py`: reproducible demo runner that performs image observation, OpenClaw decision trigger, expression, forward, turn, and sound.
- Create `tests/unit/test_openclaw_care_demo_runner.py`: validates demo sequence payloads without hardware.
- Modify `docs/project_status_2026-06-28.md`: update completion status as tasks land.

---

### Priority 1: Reproducible DK2500 Smoke Script

**Why first:** The system now works manually. The next failure mode is losing the exact working sequence. A smoke script gives both teams one repeatable command before deeper autonomy work.

**Files:**
- Create: `tools/run_dk2500_openclaw_smoke.py`
- Create: `tests/unit/test_dk2500_openclaw_smoke.py`
- Modify: `docs/project_status_2026-06-28.md`

**Interfaces:**
- Consumes: `tools.send_robot_command.build_agent_command`, runtime files under `runtime/`, base-station `/agent` URL.
- Produces:
  - `build_safe_demo_steps(device_id: str | None) -> list[dict]`
  - `check_runtime_artifacts(runtime_dir: Path) -> dict`
  - CLI command: `python tools/run_dk2500_openclaw_smoke.py --device-id xiaoan_robot_01 --runtime-dir runtime`

- [ ] **Step 1: Write unit tests for demo step construction**

Add `tests/unit/test_dk2500_openclaw_smoke.py`:

```python
from pathlib import Path
import tempfile
import unittest

from tools.run_dk2500_openclaw_smoke import build_safe_demo_steps, check_runtime_artifacts


class DK2500OpenClawSmokeTest(unittest.TestCase):
    def test_build_safe_demo_steps_uses_calibrated_motion(self):
        steps = build_safe_demo_steps("xiaoan_robot_01")

        self.assertEqual([step["payload"]["command"] for step in steps], [
            "display.expression",
            "motion.execute",
            "motion.execute",
            "audio.play_local",
        ])
        forward = steps[1]["payload"]
        self.assertEqual(forward["action"], "move_out_of_dock")
        self.assertEqual(forward["params"], {"speed": 0.56, "duration_ms": 2000})
        self.assertEqual(forward["timeout_ms"], 2200)
        turn = steps[2]["payload"]
        self.assertEqual(turn["action"], "turn")
        self.assertEqual(turn["params"], {
            "speed": 0.56,
            "angle_deg": -30.0,
            "duration_ms": 500,
        })
        self.assertEqual(turn["timeout_ms"], 700)

    def test_check_runtime_artifacts_reports_latest_jpg_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            (runtime / "latest.jpg").write_bytes(b"\xff\xd8data\xff\xd9")
            (runtime / "latest_audio.pcm").write_bytes(b"\x00\x01" * 1024)
            result = check_runtime_artifacts(runtime)

        self.assertTrue(result["latest_jpg"]["exists"])
        self.assertTrue(result["latest_jpg"]["looks_like_jpeg"])
        self.assertGreater(result["latest_audio_pcm"]["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and confirm they fail before implementation**

Run:

```powershell
python -m unittest tests.unit.test_dk2500_openclaw_smoke -v
```

Expected: FAIL with import error for `tools.run_dk2500_openclaw_smoke`.

- [ ] **Step 3: Implement smoke helper and CLI**

Create `tools/run_dk2500_openclaw_smoke.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import time
from typing import Any


DEFAULT_AGENT_URL = "ws://127.0.0.1:8765/agent"


def build_safe_demo_steps(device_id: str | None = None) -> list[dict[str, Any]]:
    base: dict[str, Any] = {}
    if device_id:
        base["device_id"] = device_id
    return [
        {
            "name": "expression_happy",
            "payload": {
                **base,
                "command": "display.expression",
                "expression": "happy",
                "duration_ms": 3000,
                "loop": False,
            },
        },
        {
            "name": "forward_out_of_base",
            "payload": {
                **base,
                "command": "motion.execute",
                "action": "move_out_of_dock",
                "action_id": f"smoke-forward-{int(time.time() * 1000)}",
                "params": {"speed": 0.56, "duration_ms": 2000},
                "timeout_ms": 2200,
                "wait_completed": True,
            },
        },
        {
            "name": "turn_to_user",
            "payload": {
                **base,
                "command": "motion.execute",
                "action": "turn",
                "action_id": f"smoke-turn-{int(time.time() * 1000)}",
                "params": {"speed": 0.56, "angle_deg": -30.0, "duration_ms": 500},
                "timeout_ms": 700,
                "wait_completed": True,
            },
        },
        {
            "name": "local_care_sound",
            "payload": {
                **base,
                "command": "audio.play_local",
                "sound": "care_01",
                "volume": 0.7,
            },
        },
    ]


def _file_info(path: Path) -> dict[str, Any]:
    exists = path.exists()
    info: dict[str, Any] = {"path": str(path), "exists": exists, "bytes": 0}
    if exists:
        info["bytes"] = path.stat().st_size
    return info


def check_runtime_artifacts(runtime_dir: Path) -> dict[str, Any]:
    latest_jpg = runtime_dir / "latest.jpg"
    latest_audio = runtime_dir / "latest_audio.pcm"
    jpg = _file_info(latest_jpg)
    if latest_jpg.exists():
        data = latest_jpg.read_bytes()
        jpg["looks_like_jpeg"] = len(data) >= 4 and data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    else:
        jpg["looks_like_jpeg"] = False
    return {
        "latest_jpg": jpg,
        "latest_audio_pcm": _file_info(latest_audio),
    }


async def send_agent_payload(url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    import websockets

    messages: list[dict[str, Any]] = []
    async with websockets.connect(url) as websocket:
        await websocket.send(json.dumps({"type": "agent.command", "payload": payload}, ensure_ascii=False))
        raw_ack = await websocket.recv()
        messages.append(json.loads(raw_ack))
        if payload.get("wait_completed"):
            raw_completed = await websocket.recv()
            messages.append(json.loads(raw_completed))
    return messages


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    artifact_before = check_runtime_artifacts(Path(args.runtime_dir))
    step_results = []
    for step in build_safe_demo_steps(args.device_id):
        messages = await send_agent_payload(args.url, step["payload"])
        step_results.append({"name": step["name"], "messages": messages})
    artifact_after = check_runtime_artifacts(Path(args.runtime_dir))
    return {
        "agent_url": args.url,
        "device_id": args.device_id,
        "artifact_before": artifact_before,
        "artifact_after": artifact_after,
        "steps": step_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DK2500/OpenClaw robot IO smoke.")
    parser.add_argument("--url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--device-id", default="xiaoan_robot_01")
    parser.add_argument("--runtime-dir", default="runtime")
    return parser.parse_args()


def main() -> None:
    result = asyncio.run(run_smoke(parse_args()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m unittest tests.unit.test_dk2500_openclaw_smoke -v
```

Expected: PASS.

- [ ] **Step 5: Hardware smoke command**

With server and robot online:

```powershell
python tools\run_dk2500_openclaw_smoke.py --device-id xiaoan_robot_01 --runtime-dir runtime
```

Expected:

- JSON summary includes `agent.ack` for each step.
- For motion steps, JSON includes `agent.motion_completed` after Priority 2 lands.
- `artifact_after.latest_jpg.exists` is `true`.
- `artifact_after.latest_jpg.looks_like_jpeg` is `true`.
- `artifact_after.latest_audio_pcm.bytes` is greater than `0` after `/audio` has streamed.

- [ ] **Step 6: Commit**

```powershell
git add tools/run_dk2500_openclaw_smoke.py tests/unit/test_dk2500_openclaw_smoke.py docs/project_status_2026-06-28.md
git commit -m "Add DK2500 OpenClaw smoke plan runner"
```

---

### Priority 2: Motion Completion Propagation Through `/agent`

**Why second:** Manual control is not enough for autonomy. The OpenClaw side must know when a motion really completed before chaining the next command.

**Files:**
- Modify: `base_station/ws_server/server.py`
- Modify: `tests/integration/test_ws_command_forwarding.py`

**Interfaces:**
- Consumes: robot `/control` message type `motion.completed` with `payload.action_id`.
- Produces:
  - `agent.motion_completed` message on `/agent`.
  - Payload shape: `{"ok": true, "action_id": "...", "result": "success", "device_id": "..."}`
  - Request flag: agent command payload `"wait_completed": true`.

- [ ] **Step 1: Write integration test for completion forwarding**

Add this test to `tests/integration/test_ws_command_forwarding.py`:

```python
    async def test_agent_motion_wait_receives_motion_completed(self) -> None:
        action_id = "agent-wait-001"
        await asyncio.wait_for(
            self.agent.send(json.dumps({
                "type": "agent.command",
                "payload": {
                    "command": "motion.execute",
                    "action": "move_out_of_dock",
                    "action_id": action_id,
                    "wait_completed": True,
                },
            }, ensure_ascii=False)),
            timeout=2,
        )

        robot_message = await self.recv_json(self.robot)
        self.assertEqual(robot_message["type"], "motion.execute")
        self.assertEqual(robot_message["payload"]["action_id"], action_id)

        ack = await self.recv_json(self.agent)
        self.assertEqual(ack["type"], "agent.ack")
        self.assertTrue(ack["payload"]["ok"])

        await asyncio.wait_for(
            self.robot.send(build_message(
                "motion.completed",
                2,
                {
                    "device_id": "test-robot-001",
                    "action_id": action_id,
                    "result": "success",
                },
            )),
            timeout=2,
        )

        completed = await self.recv_json(self.agent)
        self.assertEqual(completed["type"], "agent.motion_completed")
        self.assertEqual(completed["payload"]["action_id"], action_id)
        self.assertEqual(completed["payload"]["result"], "success")
        self.assertEqual(completed["payload"]["device_id"], "test-robot-001")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.integration.test_ws_command_forwarding.WebSocketCommandForwardingTest.test_agent_motion_wait_receives_motion_completed -v
```

Expected: FAIL or timeout because `motion.completed` is only logged and not forwarded.

- [ ] **Step 3: Implement waiter registry**

In `base_station/ws_server/server.py`, add module-level state:

```python
motion_completion_waiters: dict[str, list[asyncio.Future]] = {}
```

Add helper functions:

```python
def _register_motion_waiter(action_id: str) -> asyncio.Future:
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    motion_completion_waiters.setdefault(action_id, []).append(future)
    return future


def _resolve_motion_waiters(payload: dict) -> None:
    action_id = payload.get("action_id")
    if not action_id:
        return
    waiters = motion_completion_waiters.pop(action_id, [])
    for future in waiters:
        if not future.done():
            future.set_result(dict(payload))
```

In `reset_state_for_tests()`, clear the registry:

```python
motion_completion_waiters.clear()
```

In `handle_control()`, update the existing motion-completion logging block by calling:

```python
                _resolve_motion_waiters(payload)
```

- [ ] **Step 4: Send completion to waiting `/agent` client**

In `handle_agent()`, after `send_agent_ack(...)`, detect motion wait:

```python
                    if (
                        payload.get("command") == MessageType.MOTION_EXECUTE.value
                        and payload.get("wait_completed")
                    ):
                        action_id = robot_message.get("payload", {}).get("action_id")
                        if action_id:
                            future = _register_motion_waiter(action_id)
                            try:
                                completed_payload = await asyncio.wait_for(
                                    future,
                                    timeout=(robot_message.get("payload", {}).get("timeout_ms", 1200) / 1000.0) + 1.0,
                                )
                                await websocket.send(json.dumps({
                                    "type": "agent.motion_completed",
                                    "payload": {
                                        "ok": True,
                                        "device_id": completed_payload.get("device_id") or selected_device_id,
                                        "action_id": action_id,
                                        "result": completed_payload.get("result"),
                                    },
                                }, ensure_ascii=False))
                            except asyncio.TimeoutError:
                                await websocket.send(json.dumps({
                                    "type": "agent.motion_completed",
                                    "payload": {
                                        "ok": False,
                                        "device_id": selected_device_id,
                                        "action_id": action_id,
                                        "error": "Timed out waiting for motion.completed",
                                    },
                                }, ensure_ascii=False))
```

- [ ] **Step 5: Run focused integration tests**

Run:

```powershell
python -m unittest tests.integration.test_ws_command_forwarding -v
```

Expected: PASS.

- [ ] **Step 6: Hardware verification**

With robot online:

```powershell
python tools\run_dk2500_openclaw_smoke.py --device-id xiaoan_robot_01 --runtime-dir runtime
```

Expected: each motion step prints both `agent.ack` and `agent.motion_completed` with matching `action_id`.

- [ ] **Step 7: Commit**

```powershell
git add base_station/ws_server/server.py tests/integration/test_ws_command_forwarding.py
git commit -m "Forward motion completion to agent clients"
```

---

### Priority 3: Completion-Aware Robot Gateway and Care Skill

**Why third:** OpenClaw uses `RobotMotionSkill`; if the skill does not wait for completion, autonomous sequences can overlap or skip physical actions.

**Files:**
- Modify: `agent/core/gateway.py`
- Modify: `agent/skills/robot_motion.py`
- Modify: `tests/unit/test_robot_motion_skill.py`
- Modify: `tests/integration/test_robot_motion_skill.py`

**Interfaces:**
- `RobotGateway.send_motion(action: str, params: dict | None = None, timeout_ms: int = 5000, wait_completed: bool = False) -> dict`
- `RobotMotionSkill.move_out_of_dock(..., wait_completed: bool = False) -> dict`
- `RobotMotionSkill.care_for_user(..., wait_completed: bool = True) -> list[dict]`

- [ ] **Step 1: Update tests for gateway payloads**

Add assertions in `tests/unit/test_robot_motion_skill.py` that `care_for_user()` passes `wait_completed=True` to motion and does not call `say()` until motion returns.

Expected fake gateway calls:

```python
[
    ("expression", "caring"),
    ("motion", "move_out_of_dock", {"speed": 0.56, "distance_cm": 10.0}, 1200, True),
    ("tts", "take a short break"),
]
```

- [ ] **Step 2: Extend `RobotGateway.send_command()` to receive optional second event**

In `agent/core/gateway.py`, add an optional parameter:

```python
    async def send_command(self, command: str, wait_completed: bool = False, **payload: Any) -> dict:
```

Include the flag in the sent payload:

```python
                "wait_completed": wait_completed,
```

After reading `agent.ack`, if `wait_completed` is true, read one more message and return:

```python
        if wait_completed:
            raw_completed = await asyncio.wait_for(websocket.recv(), timeout=self.timeout_sec + 3.0)
            completed = json.loads(raw_completed)
            if completed.get("type") != "agent.motion_completed":
                raise RobotGatewayError(f"Expected agent.motion_completed, got {completed!r}")
            return {"ack": ack, "completed": completed}
```

For non-waiting commands, preserve the current return value.

- [ ] **Step 3: Pass completion wait through `send_motion()`**

Change `send_motion()`:

```python
    async def send_motion(
        self,
        action: str,
        params: dict | None = None,
        timeout_ms: int = 5000,
        wait_completed: bool = False,
    ) -> dict:
        return await self.send_command(
            "motion.execute",
            action=action,
            params=params or {},
            timeout_ms=timeout_ms,
            wait_completed=wait_completed,
        )
```

- [ ] **Step 4: Make care skill completion-aware**

In `agent/skills/robot_motion.py`, add `wait_completed` parameters and call:

```python
        results.append(await self.move_out_of_dock(
            speed=speed,
            distance_cm=distance_cm,
            timeout_ms=timeout_ms,
            wait_completed=wait_completed,
        ))
```

Default `care_for_user(..., wait_completed=True)`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.unit.test_robot_motion_skill tests.integration.test_robot_motion_skill -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add agent/core/gateway.py agent/skills/robot_motion.py tests/unit/test_robot_motion_skill.py tests/integration/test_robot_motion_skill.py
git commit -m "Wait for robot motion completion in care skill"
```

---

### Priority 4: First Autonomous Care Demo Runner

**Why fourth:** Only after the smoke script and completion semantics are stable should the demo chain perception into robot action.

**Files:**
- Create: `tools/run_openclaw_care_demo.py`
- Create: `tests/unit/test_openclaw_care_demo_runner.py`
- Modify: `docs/project_status_2026-06-28.md`

**Interfaces:**
- Consumes: latest image at `runtime/latest.jpg`, OpenClaw/Gateway config, `RobotMotionSkill`.
- Produces: one reproducible demo command:

```powershell
python tools\run_openclaw_care_demo.py --device-id xiaoan_robot_01 --image runtime\latest.jpg --sound care_01
```

- [ ] **Step 1: Write tests for demo sequence**

Create `tests/unit/test_openclaw_care_demo_runner.py`:

```python
import unittest

from tools.run_openclaw_care_demo import build_care_demo_plan


class OpenClawCareDemoRunnerTest(unittest.TestCase):
    def test_build_care_demo_plan_uses_safe_sequence(self):
        plan = build_care_demo_plan("xiaoan_robot_01", "runtime/latest.jpg", "care_01")

        self.assertEqual(plan["image"], "runtime/latest.jpg")
        self.assertEqual([step["command"] for step in plan["steps"]], [
            "observe_image",
            "display.expression",
            "motion.execute",
            "motion.execute",
            "audio.play_local",
        ])
        self.assertEqual(plan["steps"][2]["params"]["speed"], 0.56)
        self.assertEqual(plan["steps"][2]["params"]["duration_ms"], 2000)
        self.assertTrue(plan["steps"][2]["wait_completed"])
        self.assertTrue(plan["steps"][3]["wait_completed"])
```

- [ ] **Step 2: Implement dry-run demo plan builder**

Create `tools/run_openclaw_care_demo.py` with:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_care_demo_plan(device_id: str, image: str, sound: str) -> dict:
    return {
        "device_id": device_id,
        "image": image,
        "steps": [
            {"command": "observe_image", "path": image},
            {"command": "display.expression", "expression": "caring", "duration_ms": 3000},
            {
                "command": "motion.execute",
                "action": "move_out_of_dock",
                "params": {"speed": 0.56, "duration_ms": 2000},
                "timeout_ms": 2200,
                "wait_completed": True,
            },
            {
                "command": "motion.execute",
                "action": "turn",
                "params": {"speed": 0.56, "angle_deg": -30.0, "duration_ms": 500},
                "timeout_ms": 700,
                "wait_completed": True,
            },
            {"command": "audio.play_local", "sound": sound, "volume": 0.7},
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or print the OpenClaw care demo plan.")
    parser.add_argument("--device-id", default="xiaoan_robot_01")
    parser.add_argument("--image", default="runtime/latest.jpg")
    parser.add_argument("--sound", default="care_01")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not Path(args.image).exists():
        raise SystemExit(f"Image not found: {args.image}")
    plan = build_care_demo_plan(args.device_id, args.image, args.sound)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.dry_run:
        raise SystemExit("Live execution is enabled after Priority 2 and 3 completion gates pass.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests**

```powershell
python -m unittest tests.unit.test_openclaw_care_demo_runner -v
```

Expected: PASS.

- [ ] **Step 4: Enable live execution only after Priority 2 and 3 pass**

Replace the final `SystemExit` with calls to `RobotMotionSkill` only after:

- DK2500 smoke script reports `agent.motion_completed` for forward and turn.
- User confirms physical movement remains safe on the dock setup.
- The OpenClaw image-feedback call returns a non-empty observation.

Live execution should follow:

```python
await robot.show_expression("caring")
await robot.move_out_of_dock(speed=0.56, timeout_ms=2200, wait_completed=True)
await robot.gateway.send_motion("turn", params={"speed": 0.56, "angle_deg": -30.0, "duration_ms": 500}, timeout_ms=700, wait_completed=True)
await robot.gateway.send_command("audio.play_local", sound="care_01", volume=0.7)
```

- [ ] **Step 5: Hardware demo command**

```powershell
python tools\run_openclaw_care_demo.py --device-id xiaoan_robot_01 --image runtime\latest.jpg --sound care_01
```

Expected physical result:

- Face changes to caring.
- Robot moves forward with `speed=0.56`, `duration_ms=2000`.
- Robot turns toward the user for about `500ms`.
- Robot plays `care_01`.
- Logs contain image observation and matching motion completions.

- [ ] **Step 6: Commit**

```powershell
git add tools/run_openclaw_care_demo.py tests/unit/test_openclaw_care_demo_runner.py docs/project_status_2026-06-28.md
git commit -m "Add OpenClaw care demo runner"
```

---

### Priority 5: Real TTS and ASR Decision Gate

**Why fifth:** Real spoken output and ASR are valuable, but they should not block the first reliable OpenClaw robot demo.

**Files:**
- Modify: `docs/model_download.md`
- Modify: `docs/project_status_2026-06-28.md`
- Optional create after decision: `docs/tts_path_plan.md`

**Interfaces:**
- Current reliable sound: `audio.play_local care_01`.
- Current mock spoken command: `audio.play_tts` maps to mock tone.
- Future real TTS contract must be explicit: base-station text -> generated audio/PCM -> ESP32 speaker.

- [ ] **Step 1: Document demo sound policy**

Add to `docs/project_status_2026-06-28.md`:

```markdown
For public demos before real TTS lands, use `audio.play_local care_01`.
Do not describe `audio.play_tts` as spoken output; it is currently a mock tone path.
```

- [ ] **Step 2: Choose real TTS path**

Pick one of these paths and document the chosen command:

- Windows/local TTS generates PCM or WAV on base station, then robot plays it.
- DK2500-side TTS model generates PCM, then robot plays it.
- Keep spoken audio external to robot for the next public demo.

- [ ] **Step 3: Add tests only after path is chosen**

Do not add placeholder tests. Once the path is chosen, tests must assert an actual artifact contract, for example:

```python
self.assertTrue(Path("runtime/latest_tts.wav").exists())
self.assertGreater(Path("runtime/latest_tts.wav").stat().st_size, 44)
```

- [ ] **Step 4: Commit**

```powershell
git add docs/model_download.md docs/project_status_2026-06-28.md docs/tts_path_plan.md
git commit -m "Document robot TTS demo policy"
```

---

### Priority 6: Physical Route Calibration Table

**Why sixth:** After the autonomous loop works, tune it for repeatable public demonstration.

**Files:**
- Modify: `docs/project_status_2026-06-28.md`
- Optional create: `docs/hardware_motion_calibration.md`

**Interfaces:**
- Inputs: user observation of distance, direction, battery state, surface.
- Output table columns: `speed`, `duration_ms`, `distance_cm`, `turn_angle_observed`, `battery_state`, `notes`.

- [ ] **Step 1: Create calibration table**

Add:

```markdown
| Date | Command | Speed | Duration ms | Observed result | Notes |
| --- | --- | ---: | ---: | --- | --- |
| 2026-06-27 | forward | 0.56 | 1000 | about 10 cm | charged battery |
| 2026-06-27 | forward | 0.56 | 2000 | exits base | current demo setting |
| 2026-06-27 | turn left | 0.56 | 500 | visible left turn | current demo setting |
```

- [ ] **Step 2: Verify next physical run**

Run through DK2500/OpenClaw smoke and ask the user to confirm:

- moved out of base
- turned toward user
- did not overshoot
- no reboot/reconnect

- [ ] **Step 3: Commit**

```powershell
git add docs/project_status_2026-06-28.md docs/hardware_motion_calibration.md
git commit -m "Document robot demo route calibration"
```

---

## Recommended Execution Order

1. Priority 1: smoke script.
2. Priority 2: `motion.completed` bridge to `/agent`.
3. Priority 3: completion-aware `RobotGateway` and `RobotMotionSkill`.
4. Priority 4: autonomous care demo runner.
5. Priority 6: route calibration after live demo works.
6. Priority 5: real TTS/ASR only after the movement and image-feedback loop is stable, unless the next demo specifically requires spoken output.

## Final Verification Before Publishing

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -m json.tool docs\agents\08_priority_queue_results.json > $null
git diff --check
git status --short
```

For hardware verification:

```powershell
python -m base_station.ws_server.server
python tools\run_dk2500_openclaw_smoke.py --device-id xiaoan_robot_01 --runtime-dir runtime
python tools\run_openclaw_care_demo.py --device-id xiaoan_robot_01 --image runtime\latest.jpg --sound care_01
```

Expected end state:

- `/control`, `/video`, and `/audio` are all live.
- OpenClaw reads the latest robot image and logs a non-empty observation.
- Expression command succeeds.
- Forward and turn motions each report `agent.ack` and matching `agent.motion_completed`.
- Robot plays `care_01` or a verified real TTS path.
- Status docs state exactly which evidence is hardware, software, or user-observed.
