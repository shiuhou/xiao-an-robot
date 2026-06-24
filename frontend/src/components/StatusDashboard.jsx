import React, { useCallback, useEffect, useState } from "react";

import { API_BASE_URL, getHealth, getStatus, listTools } from "../api/client";
import StatusBadge from "./StatusBadge";

const API_STATUS = {
  UNKNOWN: "Unknown",
  ONLINE: "Online",
  OFFLINE: "Offline",
};

function formatValue(value) {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  return String(value);
}

export default function StatusDashboard() {
  const [apiStatus, setApiStatus] = useState(API_STATUS.UNKNOWN);
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [tools, setTools] = useState([]);
  const [errors, setErrors] = useState([]);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    setErrors([]);

    try {
      await getHealth();
      setApiStatus(API_STATUS.ONLINE);

      const [statusResult, toolsResult] = await Promise.allSettled([
        getStatus(),
        listTools(),
      ]);
      const nextErrors = [];

      if (statusResult.status === "fulfilled") {
        setRuntimeStatus(statusResult.value);
      } else {
        setRuntimeStatus(null);
        nextErrors.push(`Status: ${statusResult.reason.message}`);
      }

      if (toolsResult.status === "fulfilled") {
        setTools(toolsResult.value.tools ?? []);
      } else {
        setTools([]);
        nextErrors.push(`Tools: ${toolsResult.reason.message}`);
      }

      setErrors(nextErrors);
    } catch (requestError) {
      setApiStatus(API_STATUS.OFFLINE);
      setRuntimeStatus(null);
      setTools([]);
      setErrors([requestError.message]);
    } finally {
      setLastRefreshed(new Date());
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const components = Object.entries(runtimeStatus?.components ?? {});
  const toolNames = tools
    .map((tool) => tool?.name)
    .filter((name) => typeof name === "string" && name.length > 0);

  return (
    <div className="dashboard">
      <header className="page-header">
        <div>
          <p className="section-kicker">Xiao An Frontend MVP</p>
          <h1>Status Dashboard</h1>
          <p className="page-description">
            Local API connectivity and runtime component status.
          </p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={refresh}
          disabled={isRefreshing}
        >
          {isRefreshing ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {errors.length > 0 ? (
        <div className="error-banner" role="alert">
          <strong>
            {apiStatus === API_STATUS.OFFLINE
              ? "Local API is offline."
              : "Some status data could not be loaded."}
          </strong>
          {errors.map((error) => (
            <span key={error}>{error}</span>
          ))}
        </div>
      ) : null}

      <section className="overview-grid" aria-label="API overview">
        <div className="metric">
          <span className="metric-label">API Status</span>
          <StatusBadge status={apiStatus} />
        </div>
        <div className="metric">
          <span className="metric-label">Tools</span>
          <strong className="metric-value">{toolNames.length}</strong>
        </div>
        <div className="metric wide">
          <span className="metric-label">Last Refreshed</span>
          <strong className="metric-value compact">
            {lastRefreshed
              ? lastRefreshed.toLocaleString()
              : "Not refreshed yet"}
          </strong>
        </div>
      </section>

      <section className="dashboard-section" aria-labelledby="api-details-title">
        <div className="section-heading">
          <h2 id="api-details-title">API Details</h2>
        </div>
        <dl className="details-table">
          <div>
            <dt>API Base</dt>
            <dd>{API_BASE_URL}</dd>
          </div>
          <div>
            <dt>Service</dt>
            <dd>{formatValue(runtimeStatus?.service)}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{formatValue(runtimeStatus?.status)}</dd>
          </div>
          <div>
            <dt>Database</dt>
            <dd>{formatValue(runtimeStatus?.db_path)}</dd>
          </div>
          <div>
            <dt>Robot WebSocket</dt>
            <dd>{formatValue(runtimeStatus?.robot_ws_url)}</dd>
          </div>
          <div>
            <dt>Verbose</dt>
            <dd>{formatValue(runtimeStatus?.verbose)}</dd>
          </div>
        </dl>
      </section>

      <section
        className="dashboard-section"
        aria-labelledby="components-title"
      >
        <div className="section-heading">
          <h2 id="components-title">Components</h2>
          <span>{components.length} registered</span>
        </div>
        {components.length > 0 ? (
          <ul className="component-list">
            {components.map(([name, isReady]) => (
              <li key={name}>
                <span>{name}</span>
                <span className={`boolean-state ${isReady ? "ready" : "down"}`}>
                  {isReady ? "true" : "false"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-state">No component data available.</p>
        )}
      </section>

      <section className="dashboard-section" aria-labelledby="tools-title">
        <div className="section-heading">
          <h2 id="tools-title">Local Tools</h2>
          <span>{toolNames.length} available</span>
        </div>
        {toolNames.length > 0 ? (
          <ul className="tool-list">
            {toolNames.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        ) : (
          <p className="empty-state">No tool data available.</p>
        )}
      </section>
    </div>
  );
}
