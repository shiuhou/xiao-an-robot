# Agent Data

This directory holds the schema source for the local SQLite Event Store. The
database file itself is local runtime state and must stay ignored.

## Tracked Files

| Path | Role |
| --- | --- |
| `schema.sql` | Source schema for new local databases. |
| `migrations/` | Notes/migrations for existing local databases. |
| `.gitkeep` | Keeps this directory present in fresh checkouts. |

## Ignored Runtime Files

| Path | Rule |
| --- | --- |
| `xiao_an.db` | Local runtime database; do not commit. |
| `*.db`, `*.sqlite`, `*.sqlite3` | Local databases; ignored by `.gitignore`. |

## Boundary

The Local Event Store records local robot/runtime diagnostics, emotion events,
tool runs, and compatibility rows. It is not the primary source for user
long-term memory. OpenClaw owns that state.

## Create A Fresh Local DB

Most runtime paths initialize the schema automatically. If manual inspection is
needed, use `schema.sql` as the only source of truth for a fresh database.
