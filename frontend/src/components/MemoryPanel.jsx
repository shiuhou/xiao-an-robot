import React, { useCallback, useEffect, useState } from "react";

import {
  getProjectContext,
  listMemoryRecent,
  listNotes,
  listToolRuns,
} from "../api/client";
import JsonBlock from "./JsonBlock";
import StatusBadge from "./StatusBadge";

const TABS = [
  { id: "notes", label: "Notes" },
  { id: "recent", label: "Recent Memory" },
  { id: "tool-runs", label: "Tool Runs" },
  { id: "project-context", label: "Project Context" },
];

function normalizedLimit(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function displayValue(value) {
  return value === null || value === undefined || value === ""
    ? "Not set"
    : String(value);
}

function FilterBar({ children, onSubmit, buttonText, isLoading }) {
  return (
    <form className="memory-filter-bar" onSubmit={onSubmit}>
      <div className="memory-filter-fields">{children}</div>
      <button className="secondary-button" type="submit" disabled={isLoading}>
        {isLoading ? "Loading..." : buttonText}
      </button>
    </form>
  );
}

function NotesTab() {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState("20");
  const [notes, setNotes] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await listNotes({
        query: query.trim(),
        limit: normalizedLimit(limit, 20),
      });
      setNotes(result.notes ?? []);
    } catch (requestError) {
      setNotes([]);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }, [limit, query]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <FilterBar
        onSubmit={(event) => {
          event.preventDefault();
          load();
        }}
        buttonText={query.trim() ? "Search" : "Refresh"}
        isLoading={isLoading}
      >
        <label className="grow-field">
          <span>Search Notes</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search note content"
          />
        </label>
        <label className="limit-field">
          <span>Limit</span>
          <input
            type="number"
            min="1"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
      </FilterBar>

      {error ? <MemoryError title="Notes request failed" error={error} /> : null}
      {isLoading && notes.length === 0 ? (
        <p className="empty-state">Loading notes...</p>
      ) : notes.length > 0 ? (
        <div className="memory-list">
          {notes.map((note) => (
            <article className="memory-item" key={note.id}>
              <div className="memory-item-heading">
                <span className="entity-id">#{note.id}</span>
                <h3>{note.content}</h3>
              </div>
              <dl className="memory-metadata">
                <Metadata label="Source" value={note.source} />
                <Metadata label="Timestamp MS" value={note.timestamp_ms} />
                <Metadata label="Project" value={note.project_hint} />
              </dl>
              <div className="chip-list compact-chips">
                {(note.tags ?? []).length > 0 ? (
                  note.tags.map((tag) => (
                    <span className="chip" key={tag}>
                      {tag}
                    </span>
                  ))
                ) : (
                  <span className="muted-value">No tags</span>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">No notes found.</p>
      )}
    </>
  );
}

function RecentMemoryTab() {
  const [eventType, setEventType] = useState("");
  const [limit, setLimit] = useState("20");
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await listMemoryRecent({
        eventType: eventType.trim(),
        limit: normalizedLimit(limit, 20),
      });
      setEvents(result.events ?? []);
    } catch (requestError) {
      setEvents([]);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }, [eventType, limit]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <FilterBar
        onSubmit={(event) => {
          event.preventDefault();
          load();
        }}
        buttonText="Refresh"
        isLoading={isLoading}
      >
        <label className="grow-field">
          <span>Event Type</span>
          <input
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
            placeholder="Example: note.add"
          />
        </label>
        <label className="limit-field">
          <span>Limit</span>
          <input
            type="number"
            min="1"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
      </FilterBar>

      {error ? (
        <MemoryError title="Memory request failed" error={error} />
      ) : null}
      {isLoading && events.length === 0 ? (
        <p className="empty-state">Loading memory events...</p>
      ) : events.length > 0 ? (
        <div className="memory-list">
          {events.map((event) => (
            <article className="memory-item" key={event.id}>
              <div className="memory-item-heading">
                <span className="entity-id">#{event.id}</span>
                <h3>{event.event_type}</h3>
              </div>
              {event.text ? <p className="memory-text">{event.text}</p> : null}
              <dl className="memory-metadata">
                <Metadata label="Source" value={event.source} />
                <Metadata label="Session" value={event.session_id} />
                <Metadata
                  label="Timestamp MS"
                  value={event.timestamp_ms ?? event.created_at_ms}
                />
              </dl>
              <JsonBlock value={event.payload} label="Payload" />
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">No memory events found.</p>
      )}
    </>
  );
}

function ToolRunsTab() {
  const [toolName, setToolName] = useState("");
  const [status, setStatus] = useState("all");
  const [limit, setLimit] = useState("20");
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await listToolRuns({
        toolName: toolName.trim(),
        status,
        limit: normalizedLimit(limit, 20),
      });
      setRuns(result.tool_runs ?? []);
    } catch (requestError) {
      setRuns([]);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }, [limit, status, toolName]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <FilterBar
        onSubmit={(event) => {
          event.preventDefault();
          load();
        }}
        buttonText="Refresh"
        isLoading={isLoading}
      >
        <label className="grow-field">
          <span>Tool Name</span>
          <input
            value={toolName}
            onChange={(event) => setToolName(event.target.value)}
            placeholder="Example: note.add"
          />
        </label>
        <label>
          <span>Status</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="all">all</option>
            <option value="success">success</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <label className="limit-field">
          <span>Limit</span>
          <input
            type="number"
            min="1"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
      </FilterBar>

      {error ? (
        <MemoryError title="Tool run request failed" error={error} />
      ) : null}
      {isLoading && runs.length === 0 ? (
        <p className="empty-state">Loading tool runs...</p>
      ) : runs.length > 0 ? (
        <div className="memory-list">
          {runs.map((run) => (
            <article className="memory-item" key={run.id}>
              <div className="memory-item-heading">
                <span className="entity-id">#{run.id}</span>
                <h3>{run.tool_name}</h3>
                <StatusBadge status={run.status} />
              </div>
              <dl className="memory-metadata">
                <Metadata
                  label="Source Event"
                  value={run.source_event_type}
                />
                <Metadata
                  label="Timestamp MS"
                  value={run.timestamp_ms ?? run.created_at_ms}
                />
                <Metadata label="Error" value={run.error} />
              </dl>
              <div className="json-pair">
                <JsonBlock value={run.arguments} label="Arguments" />
                <JsonBlock value={run.result} label="Result" />
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">No tool runs found.</p>
      )}
    </>
  );
}

function ProjectContextTab() {
  const [scope, setScope] = useState("notes");
  const [limit, setLimit] = useState("5");
  const [context, setContext] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await getProjectContext({
        scope,
        limit: normalizedLimit(limit, 5),
      });
      setContext(result);
    } catch (requestError) {
      setContext(null);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }, [limit, scope]);

  useEffect(() => {
    load();
  }, [load]);

  const summary = context?.project_memory_summary ?? {};
  const recentSections = [
    ["Recent Notes", context?.recent_notes],
    ["Recent Tasks", context?.recent_tasks],
    ["Recent Reminders", context?.recent_reminders],
  ].filter(([, items]) => Array.isArray(items));

  return (
    <>
      <FilterBar
        onSubmit={(event) => {
          event.preventDefault();
          load();
        }}
        buttonText="Refresh"
        isLoading={isLoading}
      >
        <label className="grow-field">
          <span>Scope</span>
          <select value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="notes">notes</option>
            <option value="tasks">tasks</option>
            <option value="reminders">reminders</option>
          </select>
        </label>
        <label className="limit-field">
          <span>Limit</span>
          <input
            type="number"
            min="1"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
      </FilterBar>

      {error ? (
        <MemoryError title="Project context request failed" error={error} />
      ) : null}
      {isLoading && !context ? (
        <p className="empty-state">Loading project context...</p>
      ) : context ? (
        <div className="project-context-content">
          <section className="context-summary">
            <h3>Project Memory Summary</h3>
            <dl className="summary-grid">
              {Object.entries(summary).map(([key, value]) => (
                <Metadata key={key} label={key} value={value} />
              ))}
            </dl>
          </section>
          {recentSections.map(([title, items]) => (
            <section className="context-recent-section" key={title}>
              <h3>{title}</h3>
              {items.length > 0 ? (
                <ul>
                  {items.map((item, index) => (
                    <li key={item.id ?? `${title}-${index}`}>
                      {item.content ??
                        item.title ??
                        item.message ??
                        JSON.stringify(item)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted-value">No items available.</p>
              )}
            </section>
          ))}
          <JsonBlock value={context} />
        </div>
      ) : (
        <p className="empty-state">No project context loaded.</p>
      )}
    </>
  );
}

function Metadata({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{displayValue(value)}</dd>
    </div>
  );
}

function MemoryError({ title, error }) {
  return (
    <div className="inline-error memory-error" role="alert">
      <strong>{title}</strong>
      <span>{error}</span>
    </div>
  );
}

export default function MemoryPanel() {
  const [activeTab, setActiveTab] = useState("notes");

  return (
    <div className="memory-page">
      <header className="page-header compact-header">
        <div>
          <p className="section-kicker">Legacy Compatibility</p>
          <h1>Local Event Store</h1>
          <p className="page-description">
            SQLite is a local event/debug store; OpenClaw owns long-term memory.
          </p>
        </div>
      </header>

      <div className="memory-tabs" role="tablist" aria-label="Memory views">
        {TABS.map((tab) => (
          <button
            className={`memory-tab${activeTab === tab.id ? " active" : ""}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <section className="memory-workspace">
        {activeTab === "notes" && <NotesTab />}
        {activeTab === "recent" && <RecentMemoryTab />}
        {activeTab === "tool-runs" && <ToolRunsTab />}
        {activeTab === "project-context" && <ProjectContextTab />}
      </section>
    </div>
  );
}
