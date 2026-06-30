#!/usr/bin/env bash
set -e

# Initialize the Agent SQLite database from agent/data/schema.sql.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

SCHEMA_PATH="agent/data/schema.sql"
DB_PATH="agent/data/xiao_an.db"

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "[error] sqlite3 was not found. Please install sqlite3 before initializing the database."
  exit 1
fi

if [ ! -f "$SCHEMA_PATH" ]; then
  echo "[error] Missing schema file: $SCHEMA_PATH"
  exit 1
fi

if [ -f "$DB_PATH" ]; then
  printf "[warn] %s already exists. Overwrite it? [y/N] " "$DB_PATH"
  read -r answer
  case "$answer" in
    y|Y|yes|YES)
      rm -f "$DB_PATH"
      ;;
    *)
      echo "[skip] Database was left unchanged."
      exit 0
      ;;
  esac
fi

sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
echo "[done] Initialized $DB_PATH"

