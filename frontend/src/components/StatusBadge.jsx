import React from "react";

export default function StatusBadge({ status }) {
  const normalized = String(status || "Unknown").toLowerCase();

  return (
    <span className={`status-badge ${normalized}`}>
      <span className="status-dot" aria-hidden="true" />
      {status || "Unknown"}
    </span>
  );
}
