# Xiao An Runtime Debug Console

This directory contains the Electron, Vite, and React desktop frontend for Xiao
An runtime status, OpenClaw chat/debug flows, robot action debugging, emotion
timeline inspection, and local runtime logs.

The frontend does not present local tasks, reminders, memory, work activity, or
screen reports as main product capabilities. Those old backend APIs remain for
legacy compatibility and tests.

## Start The Local API

From the repository root:

```bash
python -m base_station.api.server --host 127.0.0.1 --port 8787 --db-path agent/data/xiao_an.db --verbose
```

Verify the API directly:

```bash
curl http://127.0.0.1:8787/api/health
```

The response should contain `"ok": true`.

## Install Frontend Dependencies

From `frontend/`:

```bash
npm install
```

## Start The Frontend

```bash
npm run dev
```

The renderer checks `http://127.0.0.1:8787/api/health`. If the API server is
not running, the window remains usable and displays `API Status: Offline`.

Main pages:

- Status: Local API, OpenClaw backend, robot gateway, database, components.
- Chat: send a message through XiaoAnBrain/OpenClaw and inspect results.
- Robot Debug: trigger `xiaoan.robot.*` tools manually.
- Emotion Timeline: inspect `emotion.sample`, `emotion.intervention`, and
  `companion.request` events from the Local Event Store.
- Runtime Logs: inspect tool runs, `robot.care_action`, and failed actions.

## Build

```bash
npm run build
```

The renderer build is written to `frontend/dist/`. Run `npm start` after a
successful build to open the packaged renderer in Electron.

For the complete startup, acceptance, and demo flow, see
[`docs/frontend_mvp.md`](../docs/frontend_mvp.md).
