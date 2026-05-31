# Database Migrations

This directory is reserved for future incremental SQLite database upgrades.

Use `agent/data/schema.sql` when creating a brand-new database. Use files in
`agent/data/migrations/` when an existing database needs to move from one schema
version to the next without deleting user data.

Do not commit real `.db`, `.sqlite`, or `.sqlite3` files here.

