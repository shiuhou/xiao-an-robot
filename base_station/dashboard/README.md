# Base Station Dashboard

This package serves the standalone 7-inch Dock dashboard. It is separate from
the Electron/Vite frontend and is meant for kiosk-style runtime visibility.

## Files

| Path | Role |
| --- | --- |
| `dashboard_server.py` | Standard-library HTTP server for `/dashboard`, `/api/dashboard/state`, and `/api/dashboard/today`. |
| `static/` | 1024x600 dashboard HTML/CSS/JS. |
| `data/` | Mock today/trigger data until a real trigger event store is connected. |

## Rules

- Keep the first viewport usable at 1024x600.
- Cap recent trigger/pipeline panels so the right side does not overflow.
- Do not make the dashboard depend on Electron/frontend assets.
- Treat mock JSON as placeholder data, not source of truth.

## Run

```powershell
python -m base_station.dashboard.dashboard_server
```

Open `http://127.0.0.1:8088/dashboard`.

## Related Docs

- [../../docs/runbooks/base_station_dashboard.md](../../docs/runbooks/base_station_dashboard.md)
- [../../docs/current_status.md](../../docs/current_status.md)
- [../../tests/unit/test_dashboard_server.py](../../tests/unit/test_dashboard_server.py)
