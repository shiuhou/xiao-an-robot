import React, { useCallback, useEffect, useState } from "react";

import { listMemoryRecent, listToolRuns } from "../api/client";
import JsonBlock from "./JsonBlock";
import StatusBadge from "./StatusBadge";

function timestampValue(item) {
  return item?.timestamp_ms ?? item?.created_at_ms ?? 0;
}

function formatTimestamp(item) {
  const value = timestampValue(item);
  return value ? new Date(value).toLocaleString() : "No timestamp";
}

function ToolRunItem({ run }) {
  return (
    <article className="runtime-item">
      <div className="runtime-item-heading">
        <span className="entity-id">#{run.id}</span>
        <h3>{run.tool_name}</h3>
        <StatusBadge status={run.status} />
      </div>
      <dl className="memory-metadata">
        <div>
          <dt>Source Event</dt>
          <dd>{run.source_event_type || "Not set"}</dd>
        </div>
        <div>
          <dt>Timestamp</dt>
          <dd>{formatTimestamp(run)}</dd>
        </div>
        <div>
          <dt>Error</dt>
          <dd>{run.error || "None"}</dd>
        </div>
      </dl>
      <div className="json-pair">
        <JsonBlock value={run.arguments} label="Arguments" />
        <JsonBlock value={run.result} label="Result" />
      </div>
    </article>
  );
}

function CareActionItem({ event }) {
  return (
    <article className="runtime-item">
      <div className="runtime-item-heading">
        <span className="entity-id">#{event.id}</span>
        <h3>{event.event_type}</h3>
        <span className="runtime-time">{formatTimestamp(event)}</span>
      </div>
      {event.text ? <p className="memory-text">{event.text}</p> : null}
      <dl className="memory-metadata">
        <div>
          <dt>Source</dt>
          <dd>{event.source || "Not set"}</dd>
        </div>
        <div>
          <dt>Session</dt>
          <dd>{event.session_id || "Not set"}</dd>
        </div>
      </dl>
      <JsonBlock value={event.payload} label="Payload" />
    </article>
  );
}

export default function RuntimeLogsPanel() {
  const [toolRuns, setToolRuns] = useState([]);
  const [careActions, setCareActions] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const [toolRunResult, careResult] = await Promise.all([
        listToolRuns({ limit: 30 }),
        listMemoryRecent({ eventType: "robot.care_action", limit: 20 }),
      ]);
      setToolRuns(toolRunResult.tool_runs ?? []);
      setCareActions(careResult.events ?? []);
    } catch (requestError) {
      setToolRuns([]);
      setCareActions([]);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const failedRuns = toolRuns.filter((run) => run.status === "failed");

  return (
    <div className="debug-page">
      <header className="page-header compact-header">
        <div>
          <p className="section-kicker">Xiao An Runtime Debug</p>
          <h1>Runtime Logs</h1>
          <p className="page-description">
            Recent tool runs, robot care actions, and failed local actions.
          </p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={load}
          disabled={isLoading}
        >
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error ? (
        <div className="inline-error runtime-top-error" role="alert">
          <strong>Runtime log request failed.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <section className="runtime-summary-grid" aria-label="Runtime log summary">
        <div className="metric">
          <span className="metric-label">Tool Runs</span>
          <strong className="metric-value">{toolRuns.length}</strong>
        </div>
        <div className="metric">
          <span className="metric-label">Care Actions</span>
          <strong className="metric-value">{careActions.length}</strong>
        </div>
        <div className="metric">
          <span className="metric-label">Failed Runs</span>
          <strong className="metric-value">{failedRuns.length}</strong>
        </div>
      </section>

      <div className="runtime-columns">
        <section className="runtime-list-section" aria-labelledby="tool-runs-title">
          <div className="section-heading">
            <h2 id="tool-runs-title">Recent Tool Runs</h2>
            <span>{toolRuns.length} loaded</span>
          </div>
          {isLoading && toolRuns.length === 0 ? (
            <p className="empty-state">Loading tool runs...</p>
          ) : toolRuns.length > 0 ? (
            <div className="runtime-list">
              {toolRuns.map((run) => (
                <ToolRunItem run={run} key={run.id} />
              ))}
            </div>
          ) : (
            <p className="empty-state">No tool runs found.</p>
          )}
        </section>

        <section className="runtime-list-section" aria-labelledby="care-title">
          <div className="section-heading">
            <h2 id="care-title">Robot Care Actions</h2>
            <span>{careActions.length} loaded</span>
          </div>
          {isLoading && careActions.length === 0 ? (
            <p className="empty-state">Loading care actions...</p>
          ) : careActions.length > 0 ? (
            <div className="runtime-list">
              {careActions.map((event) => (
                <CareActionItem event={event} key={event.id} />
              ))}
            </div>
          ) : (
            <p className="empty-state">No robot care actions found.</p>
          )}
        </section>
      </div>
    </div>
  );
}
