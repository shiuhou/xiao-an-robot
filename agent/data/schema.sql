CREATE TABLE IF NOT EXISTS emotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('face', 'voice')),
    emotion_tag TEXT NOT NULL,
    confidence REAL NOT NULL,
    fatigue_score REAL DEFAULT 0.0,
    polarity TEXT DEFAULT '正面'
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    user_text TEXT,
    assistant_reply TEXT,
    emotion_tag TEXT,
    skill_called TEXT
);

CREATE TABLE IF NOT EXISTS screen_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    app_name TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    category TEXT DEFAULT 'other'
);

CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_freq TEXT NOT NULL,
    current_streak INTEGER DEFAULT 0,
    last_done INTEGER
);

CREATE TABLE IF NOT EXISTS memory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_ms INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    session_id TEXT,
    project_id INTEGER,
    text TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    privacy_level TEXT NOT NULL DEFAULT 'normal',
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_events_timestamp
    ON memory_events (timestamp_ms);

CREATE INDEX IF NOT EXISTS idx_memory_events_event_type
    ON memory_events (event_type);

CREATE INDEX IF NOT EXISTS idx_memory_events_source
    ON memory_events (source);

CREATE INDEX IF NOT EXISTS idx_memory_events_session_id
    ON memory_events (session_id);

CREATE INDEX IF NOT EXISTS idx_memory_events_project_id
    ON memory_events (project_id);
