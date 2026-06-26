import React, { useState } from "react";

import { chat } from "../api/client";
import JsonBlock from "./JsonBlock";

const DEFAULT_SESSION_ID = "frontend-debug";

function normalizeError(error) {
  return error?.message || "Unable to reach the local API";
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
              {action?.source ? <small>{action.source}</small> : null}
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

function openclawToolCalls(result) {
  const raw = result?.openclaw_raw;
  if (Array.isArray(result?.tool_calls)) {
    return result.tool_calls;
  }
  if (Array.isArray(raw?.tool_calls)) {
    return raw.tool_calls;
  }
  if (Array.isArray(raw?.message?.tool_calls)) {
    return raw.message.tool_calls;
  }
  return [];
}

function ToolCallList({ result }) {
  const calls = openclawToolCalls(result);

  return (
    <div className="action-summary">
      <div className="action-summary-heading">
        <span>OpenClaw Tool Calls</span>
        <strong>{calls.length}</strong>
      </div>
      {calls.length > 0 ? (
        <ul>
          {calls.map((call, index) => (
            <li key={`${call?.name || call?.tool || "tool"}-${index}`}>
              <span>{call?.name || call?.tool || "Unknown tool"}</span>
              <small>{JSON.stringify(call?.arguments ?? call?.args ?? {})}</small>
            </li>
          ))}
        </ul>
      ) : (
        <p>No raw tool call list returned.</p>
      )}
    </div>
  );
}

export default function ChatPage() {
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
        { source: "xiao-an-runtime-debug-console" },
      );
      setResult(response);
    } catch (requestError) {
      setError(normalizeError(requestError));
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="chat-page">
      <header className="page-header compact-header">
        <div>
          <p className="section-kicker">Xiao An Runtime Debug</p>
          <h1>Chat</h1>
          <p className="page-description">
            Send frontend messages through OpenClaw and inspect replies, tool calls,
            and local action results.
          </p>
        </div>
      </header>

      <section className="workspace-panel chat-debug-panel">
        <div className="panel-heading">
          <div>
            <h2>OpenClaw Message</h2>
            <p>
              Messages go through XiaoAnBrain, OpenClaw Bridge, and ActionExecutor.
            </p>
          </div>
        </div>

        <form className="request-form" onSubmit={handleSubmit}>
          <label>
            <span>Message</span>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Example: 你好小安，陪我休息一下"
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
              <ResultField
                label="OpenClaw Event"
                value={result.openclaw_event_type}
              />
              <ResultField label="Reply Text" value={result.reply_text} />
              <ResultField label="OpenClaw Error" value={result.openclaw_error} />
            </dl>
            <div className="action-grid three-columns">
              <ToolCallList result={result} />
              <ActionList
                title="Executed Actions"
                actions={result.executed_actions ?? result.openclaw_result?.executed_actions}
              />
              <ActionList
                title="Skipped Actions"
                actions={result.skipped_actions ?? result.openclaw_result?.skipped_actions}
              />
            </div>
            <JsonBlock value={result} />
          </div>
        ) : (
          <p className="panel-empty">No OpenClaw response yet.</p>
        )}
      </section>
    </div>
  );
}
