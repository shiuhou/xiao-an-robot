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

CREATE TABLE IF NOT EXISTS work_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    timestamp_ms INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    app_name TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    activity_type TEXT NOT NULL DEFAULT 'unknown',
    project_hint TEXT,
    project_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    duration_seconds REAL,
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_work_activities_timestamp
    ON work_activities (timestamp_ms);

CREATE INDEX IF NOT EXISTS idx_work_activities_activity_type
    ON work_activities (activity_type);

CREATE INDEX IF NOT EXISTS idx_work_activities_app_name
    ON work_activities (app_name);

CREATE INDEX IF NOT EXISTS idx_work_activities_project_hint
    ON work_activities (project_hint);

CREATE INDEX IF NOT EXISTS idx_work_activities_project_id
    ON work_activities (project_id);

CREATE INDEX IF NOT EXISTS idx_work_activities_event_id
    ON work_activities (event_id);

CREATE TABLE IF NOT EXISTS tool_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    timestamp_ms INTEGER NOT NULL,
    source_event_type TEXT,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'unknown',
    error TEXT,
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tool_runs_timestamp
    ON tool_runs (timestamp_ms);

CREATE INDEX IF NOT EXISTS idx_tool_runs_tool_name
    ON tool_runs (tool_name);

CREATE INDEX IF NOT EXISTS idx_tool_runs_status
    ON tool_runs (status);

CREATE INDEX IF NOT EXISTS idx_tool_runs_source_event_type
    ON tool_runs (source_event_type);

CREATE INDEX IF NOT EXISTS idx_tool_runs_event_id
    ON tool_runs (event_id);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    timestamp_ms INTEGER NOT NULL,
    content TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'unknown',
    project_hint TEXT,
    project_id INTEGER,
    created_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    timestamp_ms INTEGER NOT NULL,
    summary_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    date TEXT,
    source TEXT NOT NULL DEFAULT 'unknown',
    project_hint TEXT,
    project_id INTEGER,
    input_range_start_ms INTEGER,
    input_range_end_ms INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_timestamp
    ON notes (timestamp_ms);

CREATE INDEX IF NOT EXISTS idx_notes_project_hint
    ON notes (project_hint);

CREATE INDEX IF NOT EXISTS idx_notes_project_id
    ON notes (project_id);

CREATE INDEX IF NOT EXISTS idx_notes_event_id
    ON notes (event_id);

CREATE INDEX IF NOT EXISTS idx_summaries_timestamp
    ON summaries (timestamp_ms);

CREATE INDEX IF NOT EXISTS idx_summaries_summary_type
    ON summaries (summary_type);

CREATE INDEX IF NOT EXISTS idx_summaries_date
    ON summaries (date);

CREATE INDEX IF NOT EXISTS idx_summaries_project_hint
    ON summaries (project_hint);

CREATE INDEX IF NOT EXISTS idx_summaries_project_id
    ON summaries (project_id);

CREATE INDEX IF NOT EXISTS idx_summaries_event_id
    ON summaries (event_id);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    due_at_ms INTEGER NOT NULL,
    fired_at_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    message TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    project_hint TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_reminders_due_at
    ON reminders (due_at_ms);

CREATE INDEX IF NOT EXISTS idx_reminders_status
    ON reminders (status);

CREATE INDEX IF NOT EXISTS idx_reminders_created_at
    ON reminders (created_at_ms);

CREATE INDEX IF NOT EXISTS idx_reminders_event_id
    ON reminders (event_id);
