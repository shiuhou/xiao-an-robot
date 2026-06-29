# Base Station Dock Dashboard

`base_station/dashboard/` provides a standalone 7-inch kiosk dashboard for the
DK-2500 Dock screen. It is separate from the Electron frontend and uses only
Python's standard-library HTTP server.

## Start

Run from the repository root:

```powershell
python -m base_station.dashboard.dashboard_server
```

Open:

```text
http://127.0.0.1:8088/dashboard
```

Useful options:

```powershell
python -m base_station.dashboard.dashboard_server --host 127.0.0.1 --port 8088
python -m base_station.dashboard.dashboard_server --data-dir base_station/dashboard/data --runtime-dir runtime
```

## API

### `GET /api/dashboard/state`

Returns dashboard-ready JSON without the local API `ok/data/error` envelope.
The response includes health state, runtime artifacts, the current pipeline,
and the latest three trigger records.

Important fields:

- `system.base_station`: `online` when the dashboard server is running.
- `robot.status`: `connected` when `base_station.ws_server.server.sessions` has
  a live robot session, otherwise `offline`.
- `robot.camera`: inferred from robot status or `runtime/latest.jpg`.
- `robot.audio`: inferred from `runtime/audio_stats.json` or
  `runtime/latest_audio.pcm`.
- `pipeline`: `Robot -> Base -> Agent -> Action` display state.
- `triggers`: capped to three items for the 1024x600 layout.

### `GET /api/dashboard/today`

Returns local mock schedule/todo/alarm data for the left-side day panel.

## Mock Data

When there is no real trigger event store, the dashboard reads:

- `base_station/dashboard/data/today.json`
- `base_station/dashboard/data/triggers.json`

`triggers.json` supports:

```json
{
  "pipeline": {
    "current_state": "idle",
    "current_trigger": null,
    "robot": "ready",
    "base_station": "ready",
    "agent": "idle",
    "action": "waiting"
  },
  "triggers": [
    {
      "time": "14:30",
      "source": "alarm",
      "title": "喝水提醒",
      "chain": "Alarm -> Agent -> Robot Voice",
      "status": "completed",
      "detail": "已播放休息提醒"
    }
  ]
}
```

Allowed trigger sources:

`schedule`, `todo`, `alarm`, `emotion`, `voice`, `manual`, `agent`, `system`

Allowed trigger statuses:

`idle`, `triggered`, `processing`, `executing`, `acked`, `completed`, `failed`,
`timeout`

## Layout Contract

The dashboard is designed for `1024x600`:

- Left 2/3: time, dock focus state, and today's schedule/todo/alarm items.
- Right 1/3 top: Base Station, Robot, Agent, Camera, Audio health.
- Right 1/3 middle: `Robot -> Base -> Agent -> Action` pipeline state.
- Right 1/3 bottom: latest three trigger records.

Each trigger record renders as two lines:

1. time + source + title
2. chain + status

If there are no trigger records, the page shows:

`暫無觸發，小安正在待命`

The page uses fixed viewport sizing and hides overflow; it should not show
scrollbars at `1024x600`.

## Verification

```powershell
python -m unittest tests.unit.test_dashboard_server
```

Manual 1024x600 check:

1. Start the dashboard server.
2. Open `http://127.0.0.1:8088/dashboard`.
3. Set the browser window to `1024x600`.
4. Confirm there are no scrollbars and the right side shows health, pipeline,
   and exactly three or fewer trigger records.
