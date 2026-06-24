# Xiao An Frontend MVP

This directory contains the Electron, Vite, and React desktop frontend.

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

## Build

```bash
npm run build
```

The renderer build is written to `frontend/dist/`. Run `npm start` after a
successful build to open the packaged renderer in Electron.

For the complete Step 29 startup, acceptance, and demo flow, see
[`docs/frontend_mvp.md`](../docs/frontend_mvp.md).
