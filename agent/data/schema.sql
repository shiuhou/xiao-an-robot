CREATE TABLE IF NOT EXISTS emotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('face', 'voice')),
    emotion_tag TEXT NOT NULL,
    confidence REAL NOT NULL,
    fatigue_score REAL DEFAULT 0.0
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
