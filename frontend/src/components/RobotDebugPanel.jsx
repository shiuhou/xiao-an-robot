import React, { useState } from "react";

import { callTool } from "../api/client";
import JsonBlock from "./JsonBlock";

const DEFAULT_SESSION_ID = "frontend-robot-debug";

function normalizeError(error) {
  return error?.message || "Unable to reach the local API";
}

function ResultSummary({ result }) {
  if (!result) {
    return <p className="panel-empty">No robot tool has been called yet.</p>;
  }

  const actionResult = result.result ?? {};
  const executed = actionResult.executed_actions ?? [];
  const skipped = actionResult.skipped_actions ?? [];

  return (
    <div className="response-area">
      <dl className="result-details">
        <div>
          <dt>Tool</dt>
          <dd>{result.tool}</dd>
        </div>
        <div>
          <dt>Session</dt>
          <dd>{result.session_id}</dd>
        </div>
        <div>
          <dt>Executed</dt>
          <dd>{executed.length}</dd>
        </div>
        <div>
          <dt>Skipped</dt>
          <dd>{skipped.length}</dd>
        </div>
      </dl>
      <JsonBlock value={result} />
    </div>
  );
}

export default function RobotDebugPanel() {
  const [expression, setExpression] = useState("caring");
  const [sayText, setSayText] = useState("我在这里，先慢慢呼吸一下。");
  const [careText, setCareText] = useState("我陪你休息一下。");
  const [sessionId, setSessionId] = useState(DEFAULT_SESSION_ID);
  const [activeTool, setActiveTool] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function runTool(tool, argumentsValue = {}) {
    setActiveTool(tool);
    setError("");
    setResult(null);
    try {
      const response = await callTool(
        tool,
        argumentsValue,
        sessionId.trim() || DEFAULT_SESSION_ID,
      );
      setResult(response);
    } catch (requestError) {
      setError(normalizeError(requestError));
    } finally {
      setActiveTool("");
    }
  }

  return (
    <div className="debug-page">
      <header className="page-header compact-header">
        <div>
          <p className="section-kicker">Xiao An Runtime Debug</p>
          <h1>Robot Debug</h1>
          <p className="page-description">
            Trigger OpenClaw-facing robot tools through the local action path.
          </p>
        </div>
      </header>

      <section className="workspace-panel debug-workspace">
        <div className="panel-heading">
          <div>
            <h2>Manual Robot Tools</h2>
            <p>
              Calls are sent to /api/tools/call and then routed through RobotGateway.
            </p>
          </div>
        </div>

        <div className="robot-debug-grid">
          <label>
            <span>Session ID</span>
            <input
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
            />
          </label>
          <label>
            <span>Expression</span>
            <input
              value={expression}
              onChange={(event) => setExpression(event.target.value)}
            />
          </label>
          <label className="span-two">
            <span>Say Text</span>
            <input
              value={sayText}
              onChange={(event) => setSayText(event.target.value)}
            />
          </label>
          <label className="span-two">
            <span>Care Text</span>
            <input
              value={careText}
              onChange={(event) => setCareText(event.target.value)}
            />
          </label>
        </div>

        <div className="robot-action-bar" aria-label="Robot debug actions">
          <button
            className="secondary-button"
            type="button"
            disabled={Boolean(activeTool)}
            onClick={() => runTool("xiaoan.robot.expression", { expression })}
          >
            {activeTool === "xiaoan.robot.expression" ? "Running..." : "Expression"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={Boolean(activeTool)}
            onClick={() => runTool("xiaoan.robot.say", { text: sayText })}
          >
            {activeTool === "xiaoan.robot.say" ? "Running..." : "Say"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={Boolean(activeTool)}
            onClick={() => runTool("xiaoan.robot.move_out")}
          >
            {activeTool === "xiaoan.robot.move_out" ? "Running..." : "Move Out"}
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={Boolean(activeTool)}
            onClick={() => runTool("xiaoan.robot.return_to_dock")}
          >
            {activeTool === "xiaoan.robot.return_to_dock"
              ? "Running..."
              : "Return"}
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={Boolean(activeTool)}
            onClick={() => runTool("xiaoan.robot.care", { text: careText })}
          >
            {activeTool === "xiaoan.robot.care" ? "Running..." : "Care"}
          </button>
        </div>

        {error ? (
          <div className="inline-error" role="alert">
            <strong>Robot tool request failed.</strong>
            <span>{error}</span>
          </div>
        ) : null}

        <ResultSummary result={result} />
      </section>
    </div>
  );
}
