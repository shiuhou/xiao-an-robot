# Active Emotion Care Demo

## Step 33 Goal

Run the full software loop for Xiao An proactive emotion care without real ESP32 hardware, real Qwen, or a real camera:

1. `emotion_runtime` emits a tired sample from the fake camera/mock emotion chain.
2. `EmotionMonitorSkill` triggers `emotion.intervention`.
3. The event is sent through the real OpenClaw Gateway to `xiaoan-runtime`.
4. `xiaoan-runtime` returns a short care reply and calls `xiaoan.robot.care`.
5. `ActionExecutor` runs the tool.
6. `base_station` forwards expression, motion, and audio commands.
7. `mock_robot` receives `caring`, `move_out_of_dock`, and TTS.
8. Local Event Store records `emotion.intervention` and `robot.care_action`.

## Preflight

Run from the repository root:

```bash
git branch --show-current
git status --short
git log --oneline -5
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
```

Expected:

- Branch: `integration/openclaw-builder-workflow`
- `git status --short` is empty before the demo
- Full tests pass
- OpenClaw Gateway is running at `ws://127.0.0.1:18789`
- `xiaoan-runtime` is available

## Gateway Smoke

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC=90 \
.venv/bin/python tools/send_frontend_message.py "你好小安" --verbose
```

```bash
XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC=90 \
.venv/bin/python tools/send_frontend_message.py "让小安出来陪我一下" --verbose
```

Expected:

- Both responses have `handled=true` and `reply_text`.
- The companion request includes `xiaoan.robot.care` or a reasonable `xiaoan.robot.say`.
- No note/task/reminder/summary/work_context tools are called.

## Three-Terminal Demo

Terminal 1:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m base_station.ws_server.server
```

Terminal 2:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/mocks/mock_robot.py --host 127.0.0.1 --port 8765
```

Terminal 3 starts each demo run.

## Tired Demo

```bash
rm -f agent/data/step33_demo.db

XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC=90 \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m base_station.monitor.emotion_runtime \
  --source fake_camera \
  --model-backend mock \
  --enable-vlm-gate \
  --vlm-backend qwen_vl \
  --pattern tired \
  --count 3 \
  --interval 0 \
  --db-path agent/data/step33_demo.db \
  --verbose
```

Successful output includes:

```json
{
  "result": {
    "handled": true,
    "route": "link_2_emotion_fast_path",
    "openclaw_event_type": "emotion.intervention",
    "openclaw_result": {
      "handled": true,
      "reply_text": "你已经工作很久了，先停一下，喝口水，放松眼睛。我陪你休息一会儿。",
      "executed_actions": [
        {"name": "robot.say"},
        {"name": "xiaoan.robot.care"}
      ]
    }
  }
}
```

The `xiaoan.robot.care` result should contain forwarded acknowledgements for:

- `display.expression`
- `motion.execute`
- `audio.play_tts` or `audio.play_local`

Frames after the first tired intervention should report:

```json
{
  "result": {
    "handled": false,
    "reason": "cooldown",
    "message": "Intervention skipped due to cooldown."
  }
}
```

## Neutral False-Trigger Check

```bash
rm -f agent/data/step33_neutral.db

XIAO_AN_OPENCLAW_BACKEND=gateway \
XIAO_AN_OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789 \
XIAO_AN_OPENCLAW_AGENT=xiaoan-runtime \
XIAO_AN_OPENCLAW_GATEWAY_TIMEOUT_SEC=90 \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m base_station.monitor.emotion_runtime \
  --source fake_face \
  --model-backend mock \
  --pattern neutral \
  --count 3 \
  --interval 0 \
  --db-path agent/data/step33_neutral.db \
  --verbose
```

Expected for all frames:

```json
{
  "result": {
    "handled": false,
    "reason": "normal",
    "message": "No intervention needed."
  }
}
```

`mock_robot` should not receive new caring, motion, or audio commands during the neutral run.

## Local Event Store Query

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import sqlite3, json

db = "agent/data/step33_demo.db"
con = sqlite3.connect(db)
cur = con.execute("""
select id, event_type, source, session_id, text, payload_json
from memory_events
where event_type in ('emotion.intervention', 'robot.care_action', 'companion.request')
order by id desc
limit 10
""")

rows = cur.fetchall()
print("rows:", len(rows))
for row in rows:
    id_, event_type, source, session_id, text, payload_json = row
    print("\n---")
    print("id:", id_)
    print("event_type:", event_type)
    print("source:", source)
    print("session_id:", session_id)
    print("text:", text)
    try:
        payload = json.loads(payload_json or "{}")
    except Exception:
        payload = payload_json
    print(json.dumps(payload, ensure_ascii=False, indent=2) if isinstance(payload, dict) else payload)
PY
```

Expected:

- At least one `emotion.intervention`
- At least one `robot.care_action`
- `robot.care_action` metadata includes expression, motion, and TTS/audio action results

## Common Failures

- Gateway unavailable: frontend or emotion runtime calls time out or cannot connect to `ws://127.0.0.1:18789`.
- Runtime agent unavailable: Gateway responds, but no `xiaoan-runtime` decision arrives.
- Base station unavailable: OpenClaw returns care actions, but local execution reports connection failure to `ws://127.0.0.1:8765/agent`.
- Mock robot not connected: `xiaoan.robot.care` may execute but lacks forwarded `display.expression`, `motion.execute`, and `audio.play_tts` acknowledgements.
- Cooldown misunderstood: only the first tired frame should intervene; later tired frames should be skipped.
- Neutral false trigger: neutral frames must stay `handled=false` with `reason=normal`.
- Database path mismatch: querying the wrong DB will miss `emotion.intervention` and `robot.care_action`.

## Step 34 Entry Conditions

Proceed to Step 34 only when:

- Step 33 tired demo passes end to end through real OpenClaw Gateway and `xiaoan-runtime`.
- `mock_robot` receives expression, motion, and audio acknowledgements from `xiaoan.robot.care`.
- Neutral samples do not trigger care actions.
- Local Event Store contains both `emotion.intervention` and `robot.care_action`.
- Full unit/integration test discovery passes after the documentation update.
- No runtime OpenClaw permissions were weakened, and no real ESP32, real Qwen, or real camera was required.
