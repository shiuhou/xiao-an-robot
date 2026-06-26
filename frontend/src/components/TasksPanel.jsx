import React, { useCallback, useEffect, useState } from "react";

import {
  cancelTask,
  completeTask,
  createTask,
  listTasks,
} from "../api/client";
import JsonBlock from "./JsonBlock";
import StatusBadge from "./StatusBadge";

const DEFAULT_FORM = {
  title: "",
  description: "",
  priority: "normal",
  dueText: "",
  sessionId: "default",
};

function displayValue(value) {
  return value === null || value === undefined || value === ""
    ? "Not set"
    : String(value);
}

export default function TasksPanel() {
  const [tasks, setTasks] = useState([]);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [activeAction, setActiveAction] = useState("");
  const [lastResponse, setLastResponse] = useState(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await listTasks({ includeDone: true, limit: 20 });
      setTasks(result.tasks ?? []);
    } catch (requestError) {
      setTasks([]);
      setError(requestError.message);
    } finally {
      setIsLoading(false);
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
    const title = form.title.trim();
    if (!title) {
      setError("Task title is required.");
      return;
    }

    setIsCreating(true);
    setError("");
    try {
      const result = await createTask({
        title,
        description: form.description.trim() || undefined,
        priority: form.priority,
        dueText: form.dueText.trim() || undefined,
        sessionId: form.sessionId.trim() || "default",
      });
      setLastResponse(result);
      setForm((current) => ({
        ...DEFAULT_FORM,
        sessionId: current.sessionId || "default",
      }));
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsCreating(false);
    }
  }

  async function runTaskAction(action, taskId, sessionId = "default") {
    const actionKey = `${action}-${taskId}`;
    setActiveAction(actionKey);
    setError("");
    try {
      const result =
        action === "complete"
          ? await completeTask(taskId, sessionId)
          : await cancelTask(taskId, sessionId);
      setLastResponse(result);
      await refresh();
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
          <p className="section-kicker">Legacy Compatibility</p>
          <h1>Local Tasks</h1>
          <p className="page-description">
            Local task APIs remain for compatibility; OpenClaw owns product tasks.
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
          <strong>Task request failed.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <section className="resource-section" aria-labelledby="add-task-title">
        <div className="section-heading">
          <h2 id="add-task-title">Add Task</h2>
        </div>
        <form className="entity-form" onSubmit={handleCreate}>
          <label className="span-two">
            <span>Title *</span>
            <input
              value={form.title}
              onChange={(event) => updateForm("title", event.target.value)}
              placeholder="Finish the current frontend step"
            />
          </label>
          <label>
            <span>Priority</span>
            <select
              value={form.priority}
              onChange={(event) => updateForm("priority", event.target.value)}
            >
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
            </select>
          </label>
          <label>
            <span>Due Text</span>
            <input
              value={form.dueText}
              onChange={(event) => updateForm("dueText", event.target.value)}
              placeholder="Tomorrow afternoon"
            />
          </label>
          <label className="span-two">
            <span>Description</span>
            <textarea
              value={form.description}
              onChange={(event) =>
                updateForm("description", event.target.value)
              }
              rows={3}
              placeholder="Optional task details"
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
              {isCreating ? "Adding..." : "Add Task"}
            </button>
          </div>
        </form>
      </section>

      <section className="resource-section" aria-labelledby="task-list-title">
        <div className="section-heading">
          <h2 id="task-list-title">Task List</h2>
          <span>{tasks.length} items</span>
        </div>
        {isLoading && tasks.length === 0 ? (
          <p className="empty-state">Loading tasks...</p>
        ) : tasks.length > 0 ? (
          <div className="entity-list">
            {tasks.map((task) => {
              const isPending = task.status === "pending";
              return (
                <article className="entity-item" key={task.id}>
                  <div className="entity-main">
                    <div className="entity-title-row">
                      <span className="entity-id">#{task.id}</span>
                      <h3>{task.title}</h3>
                      <StatusBadge status={task.status} />
                    </div>
                    {task.description ? (
                      <p className="entity-description">{task.description}</p>
                    ) : null}
                    <dl className="entity-metadata">
                      <div>
                        <dt>Priority</dt>
                        <dd>{displayValue(task.priority)}</dd>
                      </div>
                      <div>
                        <dt>Due Text</dt>
                        <dd>{displayValue(task.due_text)}</dd>
                      </div>
                      <div>
                        <dt>Due At MS</dt>
                        <dd>{displayValue(task.due_at_ms)}</dd>
                      </div>
                    </dl>
                  </div>
                  {isPending ? (
                    <div className="entity-actions">
                      <button
                        className="small-button"
                        type="button"
                        disabled={Boolean(activeAction)}
                        onClick={() =>
                          runTaskAction(
                            "complete",
                            task.id,
                            form.sessionId || "default",
                          )
                        }
                      >
                        {activeAction === `complete-${task.id}`
                          ? "Completing..."
                          : "Complete"}
                      </button>
                      <button
                        className="small-button danger"
                        type="button"
                        disabled={Boolean(activeAction)}
                        onClick={() =>
                          runTaskAction(
                            "cancel",
                            task.id,
                            form.sessionId || "default",
                          )
                        }
                      >
                        {activeAction === `cancel-${task.id}`
                          ? "Cancelling..."
                          : "Cancel"}
                      </button>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : (
          <p className="empty-state">No tasks found.</p>
        )}
      </section>

      <JsonBlock value={lastResponse} label="Last API Response" />
    </div>
  );
}
