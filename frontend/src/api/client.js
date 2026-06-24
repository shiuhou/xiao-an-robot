export const API_BASE_URL = "http://127.0.0.1:8787";

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 4000);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...options.headers,
      },
      signal: controller.signal,
    });
    const payload = await response.json();

    if (!response.ok || !payload.ok) {
      const message = payload?.error?.message || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload.data;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("API request timed out");
    }
    throw new Error(error?.message || "Unable to reach the local API");
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function postJson(path, body) {
  return request(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

function withQuery(path, params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export function getHealth() {
  return request("/api/health");
}

export function getStatus() {
  return request("/api/status");
}

export function listTools() {
  return request("/api/tools");
}

export function chat(text, sessionId = "default", metadata = {}) {
  return postJson("/api/chat", {
    text,
    session_id: sessionId,
    metadata,
  });
}

export function previewContext(text, sessionId = "default") {
  return postJson("/api/context/preview", {
    text,
    session_id: sessionId,
  });
}

export function listTasks({ includeDone = true, limit = 20 } = {}) {
  return request(
    withQuery("/api/tasks", {
      include_done: includeDone,
      limit,
    }),
  );
}

export function createTask({
  title,
  description,
  priority = "normal",
  dueText,
  dueAtMs,
  projectHint,
  sessionId = "default",
}) {
  return postJson("/api/tasks", {
    title,
    description,
    priority,
    due_text: dueText,
    due_at_ms: dueAtMs,
    project_hint: projectHint,
    session_id: sessionId,
  });
}

export function completeTask(taskId, sessionId = "default") {
  return postJson(`/api/tasks/${taskId}/complete`, {
    session_id: sessionId,
  });
}

export function cancelTask(taskId, sessionId = "default") {
  return postJson(`/api/tasks/${taskId}/cancel`, {
    session_id: sessionId,
  });
}

export function listReminders({ includeFired = true, limit = 20 } = {}) {
  return request(
    withQuery("/api/reminders", {
      include_fired: includeFired,
      limit,
    }),
  );
}

export function createReminder({
  message,
  delaySeconds,
  dueAtMs,
  dueText,
  projectHint,
  sessionId = "default",
}) {
  return postJson("/api/reminders", {
    message,
    delay_seconds: delaySeconds,
    due_at_ms: dueAtMs,
    due_text: dueText,
    project_hint: projectHint,
    session_id: sessionId,
  });
}

export function cancelReminder(reminderId, sessionId = "default") {
  return postJson(`/api/reminders/${reminderId}/cancel`, {
    session_id: sessionId,
  });
}

export function listDueReminders({ limit = 20 } = {}) {
  return request(withQuery("/api/reminders/due", { limit }));
}

export function markReminderFired(reminderId, sessionId = "default") {
  return postJson(`/api/reminders/${reminderId}/mark-fired`, {
    session_id: sessionId,
  });
}

export function listNotes({ query = "", limit = 20 } = {}) {
  return request(withQuery("/api/notes", { q: query, limit }));
}

export function listMemoryRecent({ eventType = "", limit = 20 } = {}) {
  return request(
    withQuery("/api/memory/recent", {
      event_type: eventType,
      limit,
    }),
  );
}

export function listToolRuns({
  toolName = "",
  status = "",
  limit = 20,
} = {}) {
  return request(
    withQuery("/api/tool-runs", {
      tool_name: toolName,
      status: status === "all" ? "" : status,
      limit,
    }),
  );
}

export function getProjectContext({ scope = "notes", limit = 5 } = {}) {
  return request(withQuery("/api/project/context", { scope, limit }));
}
