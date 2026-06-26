import React, { useCallback, useEffect, useState } from "react";

import { listMemoryRecent } from "../api/client";
import JsonBlock from "./JsonBlock";

const EVENT_TYPES = [
  "emotion.sample",
  "emotion.intervention",
  "companion.request",
];

function eventTimestamp(event) {
  return event?.timestamp_ms ?? event?.created_at_ms ?? 0;
}

function formatTimestamp(event) {
  const value = eventTimestamp(event);
  if (!value) {
    return "No timestamp";
  }
  return new Date(value).toLocaleString();
}

function EventItem({ event }) {
  const payload = event.payload ?? {};

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
          <dt>Emotion</dt>
          <dd>{payload.emotion_tag || "Not set"}</dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{payload.reason || payload.trigger_reason || "Not set"}</dd>
        </div>
      </dl>
      <JsonBlock value={payload} label="Payload" />
    </article>
  );
}

export default function EmotionTimelinePanel() {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const results = await Promise.all(
        EVENT_TYPES.map((eventType) =>
          listMemoryRecent({ eventType, limit: 20 }),
        ),
      );
      const merged = results
        .flatMap((result) => result.events ?? [])
        .sort((left, right) => eventTimestamp(right) - eventTimestamp(left))
        .slice(0, 40);
      setEvents(merged);
    } catch (requestError) {
      setEvents([]);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="debug-page">
      <header className="page-header compact-header">
        <div>
          <p className="section-kicker">Xiao An Runtime Debug</p>
          <h1>Emotion Timeline</h1>
          <p className="page-description">
            Recent local emotion samples, interventions, and companion requests.
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

      <section className="runtime-list-section" aria-label="Emotion events">
        {error ? (
          <div className="inline-error" role="alert">
            <strong>Timeline request failed.</strong>
            <span>{error}</span>
          </div>
        ) : null}

        {isLoading && events.length === 0 ? (
          <p className="empty-state">Loading runtime events...</p>
        ) : events.length > 0 ? (
          <div className="runtime-list">
            {events.map((event) => (
              <EventItem event={event} key={`${event.event_type}-${event.id}`} />
            ))}
          </div>
        ) : (
          <p className="empty-state">No emotion timeline events found.</p>
        )}
      </section>
    </div>
  );
}
