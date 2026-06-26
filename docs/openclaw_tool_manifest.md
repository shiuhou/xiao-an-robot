# OpenClaw Xiao An Tool Manifest

Status: Step 30.2 OpenClaw-facing robot body tools.

This manifest is the recommended tool surface for OpenClaw `xiaoan-runtime`.
It focuses on Xiao An's physical robot abilities, local emotion snapshot, and
runtime status. User profile, long-term memory, reminders, tasks, notes,
summaries, and work context remain OpenClaw-owned or legacy compatibility.

Code source: `agent/core/xiaoan_tool_manifest.py`.

## Recommended Tools

### `xiaoan.robot.say`

- Purpose: speak a short sentence through the robot TTS path.
- Parameters:
  - `text` string, required. Short text for Xiao An to say.
- Success:
  - `{"ok": true, "tool": "xiaoan.robot.say", "result": {...}}`
- Failure:
  - `{"ok": false, "error": "missing_text"}`
  - Robot gateway failures are recorded as failed tool runs.

### `xiaoan.robot.expression`

- Purpose: show a named facial expression on the robot display.
- Parameters:
  - `expression` string, required. Example: `neutral`, `happy`, `caring`, `calm`.
  - `duration_ms` integer, optional.
  - `loop` boolean, optional.
- Success:
  - `{"ok": true, "tool": "xiaoan.robot.expression", "result": {...}}`
- Failure:
  - `{"ok": false, "error": "missing_expression"}`
  - Robot gateway failures are recorded as failed tool runs.

### `xiaoan.robot.move_out`

- Purpose: move Xiao An a short safe distance out of the dock.
- Parameters: none.
- Success:
  - `{"ok": true, "tool": "xiaoan.robot.move_out", "result": {...}}`
- Failure:
  - Robot gateway failures are recorded as failed tool runs.

### `xiaoan.robot.return_to_dock`

- Purpose: return Xiao An to the dock through the robot motion path.
- Parameters: none.
- Success:
  - `{"ok": true, "tool": "xiaoan.robot.return_to_dock", "result": {...}}`
- Failure:
  - Robot gateway failures are recorded as failed tool runs.

### `xiaoan.robot.care`

- Purpose: run Xiao An's local active-care sequence.
- Parameters:
  - `text` string, optional. Short care message to speak.
- Success:
  - `{"ok": true, "tool": "xiaoan.robot.care", "actions": [...]}`
- Failure:
  - Robot gateway failures are recorded as failed tool runs.

### `xiaoan.breathing.start`

- Purpose: start a short local breathing-guide interaction.
- Parameters:
  - `text` string, optional. Opening guidance text.
- Success:
  - `{"ok": true, "tool": "xiaoan.breathing.start", "actions": [...]}`
- Failure:
  - Robot gateway failures are recorded as failed tool runs.

### `xiaoan.emotion.snapshot`

- Purpose: read the latest local emotion summary from the Local Event Store.
- Parameters:
  - `seconds` integer, optional. Lookback window in seconds. Default: `300`.
- Success:
  - `{"ok": true, "tool": "xiaoan.emotion.snapshot", "snapshot": {...}}`
- Failure:
  - `{"ok": false, "tool": "xiaoan.emotion.snapshot", "error": "emotion_store_unavailable"}`

### `xiaoan.runtime.status`

- Purpose: read local Xiao An runtime status and ownership boundary.
- Parameters: none.
- Success:
  - `{"ok": true, "tool": "xiaoan.runtime.status", "status": {...}}`
- Failure:
  - `{"ok": false, "tool": "xiaoan.runtime.status", "error": "runtime_status_unavailable"}`

## Compatibility Strategy

The execution layer still accepts old robot tool names:

- `robot.say` -> `xiaoan.robot.say`
- `robot.expression` -> `xiaoan.robot.expression`
- `robot.move_out` -> `xiaoan.robot.move_out`
- `robot.move_out_of_dock` -> `xiaoan.robot.move_out`
- `robot.return_to_dock` -> `xiaoan.robot.return_to_dock`
- `robot.care` / `robot.care_for_user` -> `xiaoan.robot.care`

Legacy local tools remain callable for old tests and local clients, but they
are not recommended to OpenClaw as Xiao An robot body tools:

- `note.*`
- `task.*`
- `reminder.*`
- `summary.*`
- `work_context.*`

`GET /api/tools` returns the recommended `xiaoan.*` tools in `tools` and the
compatibility names in `legacy_tools`.
