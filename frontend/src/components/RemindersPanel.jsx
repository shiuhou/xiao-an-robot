import React, { useCallback, useEffect, useState } from "react";

import {
  cancelReminder,
  createReminder,
  listDueReminders,
  listReminders,
  markReminderFired,
} from "../api/client";
import JsonBlock from "./JsonBlock";
import StatusBadge from "./StatusBadge";

const DEFAULT_FORM = {
  message: "",
  delaySeconds: "60",
  dueText: "",
  sessionId: "default",
};

function displayValue(value) {
  return value === null || value === undefined || value === ""
    ? "Not set"
    : String(value);
}

export default function RemindersPanel() {
  const [reminders, setReminders] = useState([]);
  const [dueReminders, setDueReminders] = useState([]);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDue, setIsLoadingDue] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [activeAction, setActiveAction] = useState("");
  const [lastResponse, setLastResponse] = useState(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await listReminders({ includeFired: true, limit: 20 });
      setReminders(result.reminders ?? []);
    } catch (requestError) {
      setReminders([]);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refreshDue = useCallback(async () => {
    setIsLoadingDue(true);
    setError("");
    try {
      const result = await listDueReminders({ limit: 20 });
      setDueReminders(result.reminders ?? []);
    } catch (requestError) {
      setDueReminders([]);
      setError(requestError.message);
    } finally {
      setIsLoadingDue(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleCreate(event) {
    event.preventDefault();
    const message = form.message.trim();
    if (!message) {
      setError("Reminder message is required.");
      return;
    }
    const delaySeconds = Number(form.delaySeconds);
    if (!Number.isFinite(delaySeconds)) {
      setError("Delay seconds must be a number.");
      return;
    }

    setIsCreating(true);
    setError("");
    try {
      const result = await createReminder({
        message,
        delaySeconds,
        dueText: form.dueText.trim() || undefined,
        sessionId: form.sessionId.trim() || "default",
      });
      setLastResponse(result);
      setForm((current) => ({
        ...DEFAULT_FORM,
        sessionId: current.sessionId || "default",
      }));
      await Promise.all([refresh(), refreshDue()]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsCreating(false);
    }
  }

  async function handleCancel(reminderId) {
    const actionKey = `cancel-${reminderId}`;
    setActiveAction(actionKey);
    setError("");
    try {
      const result = await cancelReminder(
        reminderId,
        form.sessionId.trim() || "default",
      );
      setLastResponse(result);
      await Promise.all([refresh(), refreshDue()]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setActiveAction("");
    }
  }

  async function handleMarkFired(reminderId) {
    const actionKey = `fire-${reminderId}`;
    setActiveAction(actionKey);
    setError("");
    try {
      const result = await markReminderFired(
        reminderId,
        form.sessionId.trim() || "default",
      );
      setLastResponse(result);
      await Promise.all([refresh(), refreshDue()]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setActiveAction("");
    }
  }

  return (
    <div className="resource-page">
      <header className="page-header">
        <div>
          <p className="section-kicker">Xiao An Frontend MVP</p>
          <h1>Reminders</h1>
          <p className="page-description">
            Schedule, inspect, and close local reminders.
          </p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={refresh}
          disabled={isLoading}
        >
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error ? (
        <div className="error-banner" role="alert">
          <strong>Reminder request failed.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <section className="resource-section" aria-labelledby="add-reminder-title">
        <div className="section-heading">
          <h2 id="add-reminder-title">Add Reminder</h2>
        </div>
        <form className="entity-form" onSubmit={handleCreate}>
          <label className="span-two">
            <span>Message *</span>
            <input
              value={form.message}
              onChange={(event) => updateForm("message", event.target.value)}
              placeholder="Take a short break"
            />
          </label>
          <label>
            <span>Delay Seconds</span>
            <input
              type="number"
              min="1"
              step="1"
              value={form.delaySeconds}
              onChange={(event) =>
                updateForm("delaySeconds", event.target.value)
              }
            />
          </label>
          <label>
            <span>Due Text</span>
            <input
              value={form.dueText}
              onChange={(event) => updateForm("dueText", event.target.value)}
              placeholder="In one minute"
            />
          </label>
          <label>
            <span>Session ID</span>
            <input
              value={form.sessionId}
              onChange={(event) => updateForm("sessionId", event.target.value)}
            />
          </label>
          <div className="form-action-cell">
            <button
              className="primary-button"
              type="submit"
              disabled={isCreating}
            >
              {isCreating ? "Adding..." : "Add Reminder"}
            </button>
          </div>
        </form>
      </section>

      <section
        className="resource-section"
        aria-labelledby="reminder-list-title"
      >
        <div className="section-heading">
          <h2 id="reminder-list-title">Reminder List</h2>
          <span>{reminders.length} items</span>
        </div>
        {isLoading && reminders.length === 0 ? (
          <p className="empty-state">Loading reminders...</p>
        ) : reminders.length > 0 ? (
          <div className="entity-list">
            {reminders.map((reminder) => (
              <article className="entity-item" key={reminder.id}>
                <div className="entity-main">
                  <div className="entity-title-row">
                    <span className="entity-id">#{reminder.id}</span>
                    <h3>{reminder.message}</h3>
                    <StatusBadge status={reminder.status} />
                  </div>
                  <dl className="entity-metadata">
                    <div>
                      <dt>Due At MS</dt>
                      <dd>{displayValue(reminder.due_at_ms)}</dd>
                    </div>
                    <div>
                      <dt>Fired At MS</dt>
                      <dd>{displayValue(reminder.fired_at_ms)}</dd>
                    </div>
                  </dl>
                </div>
                {reminder.status === "pending" ? (
                  <div className="entity-actions">
                    <button
                      className="small-button danger"
                      type="button"
                      disabled={Boolean(activeAction)}
                      onClick={() => handleCancel(reminder.id)}
                    >
                      {activeAction === `cancel-${reminder.id}`
                        ? "Cancelling..."
                        : "Cancel"}
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-state">No reminders found.</p>
        )}
      </section>

      <section className="resource-section" aria-labelledby="due-list-title">
        <div className="section-heading">
          <h2 id="due-list-title">Due Reminders</h2>
          <button
            className="text-button"
            type="button"
            onClick={refreshDue}
            disabled={isLoadingDue}
          >
            {isLoadingDue ? "Querying..." : "Query Due Reminders"}
          </button>
        </div>
        {dueReminders.length > 0 ? (
          <div className="entity-list compact-list">
            {dueReminders.map((reminder) => (
              <article className="entity-item" key={reminder.id}>
                <div className="entity-main">
                  <div className="entity-title-row">
                    <span className="entity-id">#{reminder.id}</span>
                    <h3>{reminder.message}</h3>
                    <StatusBadge status={reminder.status} />
                  </div>
                  <dl className="entity-metadata">
                    <div>
                      <dt>Due At MS</dt>
                      <dd>{displayValue(reminder.due_at_ms)}</dd>
                    </div>
                  </dl>
                </div>
                <div className="entity-actions">
                  <button
                    className="small-button"
                    type="button"
                    disabled={Boolean(activeAction)}
                    onClick={() => handleMarkFired(reminder.id)}
                  >
                    {activeAction === `fire-${reminder.id}`
                      ? "Marking..."
                      : "Mark Fired"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-state">
            {isLoadingDue
              ? "Checking due reminders..."
              : "Query due reminders to see pending items."}
          </p>
        )}
      </section>

      <JsonBlock value={lastResponse} label="Last API Response" />
    </div>
  );
}
