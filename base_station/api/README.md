# Base Station Local API

This package provides the local HTTP debug API used by the frontend/runtime
console. It is not the primary product API and it is not the owner of user
memory, reminders, tasks, or reports.

## Files

| File | Role |
| --- | --- |
| `server.py` | CLI/server entrypoint. |
| `router.py` | HTTP route dispatch and request parsing. |
| `runtime.py` | Runtime state, Local Event Store access, and component status helpers. |
| `response.py` | Shared API response envelope helpers. |

## Rules

- Keep routes debug/integration oriented.
- Treat SQLite as a Local Event Store only.
- Do not expose raw camera/audio captures or local secrets through this API.
- Keep OpenClaw-owned product domains documented as OpenClaw-owned.

## Run

```powershell
python -m base_station.api.server --host 127.0.0.1 --port 8787 --db-path agent/data/xiao_an.db --verbose
```

## Related Docs

- [../../docs/setup/local_api.md](../../docs/setup/local_api.md)
- [../../frontend/README.md](../../frontend/README.md)
- [../../agent/data/README.md](../../agent/data/README.md)
