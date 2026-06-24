import React, { useState } from "react";

import { chat, previewContext } from "../api/client";
import JsonBlock from "./JsonBlock";

const DEFAULT_SESSION_ID = "default";

function normalizeError(error) {
  return error?.message || "Unable to reach the local API";
}

function ActionList({ title, actions }) {
  const items = Array.isArray(actions) ? actions : [];

  return (
    <div className="action-summary">
      <div className="action-summary-heading">
        <span>{title}</span>
        <strong>{items.length}</strong>
      </div>
      {items.length > 0 ? (
        <ul>
          {items.map((action, index) => (
            <li key={`${action?.name || "action"}-${index}`}>
              <span>{action?.name || "Unknown action"}</span>
              {action?.reason ? <small>{action.reason}</small> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p>None</p>
      )}
    </div>
  );
}

function ResultField({ label, value }) {
  const displayed =
    value === null || value === undefined || value === "" ? "Not provided" : value;

  return (
    <div>
      <dt>{label}</dt>
      <dd>{String(displayed)}</dd>
    </div>
  );
}

function ChatMessagePanel() {
  const [text, setText] = useState("");
  const [sessionId, setSessionId] = useState(DEFAULT_SESSION_ID);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    const activeText = text.trim();
    if (!activeText) {
      setError("Enter a message before sending.");
      return;
    }

    setIsSending(true);
    setError("");
    setResult(null);
    try {
      const response = await chat(
        activeText,
        sessionId.trim() || DEFAULT_SESSION_ID,
        { source: "xiao-an-frontend" },
      );
      setResult(response);
    } catch (requestError) {
      setError(normalizeError(requestError));
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className="workspace-panel" aria-labelledby="chat-message-title">
      <div className="panel-heading">
        <div>
          <h2 id="chat-message-title">Chat Message</h2>
          <p>Send a frontend message through the local Xiao An brain.</p>
        </div>
      </div>

      <form className="request-form" onSubmit={handleSubmit}>
        <label>
          <span>Message</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Ask Xiao An something..."
            rows={5}
          />
        </label>
        <div className="form-footer">
          <label className="session-field">
            <span>Session ID</span>
            <input
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
            />
          </label>
          <button className="primary-button" type="submit" disabled={isSending}>
            {isSending ? "Sending..." : "Send"}
          </button>
        </div>
      </form>

      {error ? (
        <div className="inline-error" role="alert">
          <strong>Chat request failed.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {result ? (
        <div className="response-area">
          <dl className="result-details">
            <ResultField label="Handled" value={result.handled} />
            <ResultField label="Route" value={result.route} />
            <ResultField label="Reason" value={result.reason} />
            <ResultField label="Reply Text" value={result.reply_text} />
          </dl>
          <div className="action-grid">
            <ActionList
              title="Executed Actions"
              actions={result.executed_actions}
            />
            <ActionList
              title="Skipped Actions"
              actions={result.skipped_actions}
            />
          </div>
          <JsonBlock value={result} />
        </div>
      ) : (
        <p className="panel-empty">No chat response yet.</p>
      )}
    </section>
  );
}

function ChipList({ values, emptyText }) {
  const items = Array.isArray(values) ? values : [];
  if (items.length === 0) {
    return <span className="muted-value">{emptyText}</span>;
  }

  return (
    <div className="chip-list">
      {items.map((value) => (
        <span className="chip" key={value}>
          {value}
        </span>
      ))}
    </div>
  );
}

function ContextPreviewPanel() {
  const [text, setText] = useState("");
  const [sessionId, setSessionId] = useState(DEFAULT_SESSION_ID);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    const activeText = text.trim();
    if (!activeText) {
      setError("Enter text before previewing context.");
      return;
    }

    setIsLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await previewContext(
        activeText,
        sessionId.trim() || DEFAULT_SESSION_ID,
      );
      setResult(response);
    } catch (requestError) {
      setError(normalizeError(requestError));
    } finally {
      setIsLoading(false);
    }
  }

  const policy = result?.context?.context_policy ?? {};
  const projectSummary =
    result?.context?.project_memory?.project_memory_summary ?? null;

  return (
    <section className="workspace-panel" aria-labelledby="context-preview-title">
      <div className="panel-heading">
        <div>
          <h2 id="context-preview-title">Context Preview</h2>
          <p>Inspect context construction without executing tools or actions.</p>
        </div>
      </div>

      <form className="request-form" onSubmit={handleSubmit}>
        <label>
          <span>Preview Text</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Example: What tasks are still pending?"
            rows={5}
          />
        </label>
        <div className="form-footer">
          <label className="session-field">
            <span>Session ID</span>
            <input
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
            />
          </label>
          <button className="primary-button" type="submit" disabled={isLoading}>
            {isLoading ? "Loading..." : "Preview"}
          </button>
        </div>
      </form>

      {error ? (
        <div className="inline-error" role="alert">
          <strong>Context preview failed.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {result ? (
        <div className="response-area">
          <div className="preview-section">
            <span className="result-label">Requested Scopes</span>
            <ChipList
              values={result.requested_scopes}
              emptyText="No memory scopes requested"
            />
          </div>

          <div className="preview-section">
            <span className="result-label">Context Policy</span>
            <dl className="policy-grid">
              <ResultField label="Method" value={policy.method} />
              <ResultField label="Reason" value={policy.reason} />
              <ResultField label="Confidence" value={policy.confidence} />
            </dl>
            <div className="keyword-row">
              <span>Matched Keywords</span>
              <ChipList
                values={policy.matched_keywords}
                emptyText="No matched keywords"
              />
            </div>
          </div>

          <div className="preview-section">
            <span className="result-label">Project Memory Summary</span>
            {projectSummary ? (
              <dl className="summary-grid">
                {Object.entries(projectSummary).map(([key, value]) => (
                  <ResultField key={key} label={key} value={value} />
                ))}
              </dl>
            ) : (
              <span className="muted-value">
                No project memory summary was injected.
              </span>
            )}
          </div>

          <JsonBlock value={result} />
        </div>
      ) : (
        <p className="panel-empty">No context preview yet.</p>
      )}
    </section>
  );
}

export default function ChatPage() {
  return (
    <div className="chat-page">
      <header className="page-header compact-header">
        <div>
          <p className="section-kicker">Xiao An Frontend MVP</p>
          <h1>Chat & Context Preview</h1>
          <p className="page-description">
            Exercise the frontend message route and inspect its memory context.
          </p>
        </div>
      </header>

      <div className="chat-workspaces">
        <ChatMessagePanel />
        <ContextPreviewPanel />
      </div>
    </div>
  );
}
