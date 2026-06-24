import React, { useState } from "react";

export default function JsonBlock({ value, label = "Raw JSON" }) {
  const [isOpen, setIsOpen] = useState(false);

  if (value === null || value === undefined) {
    return null;
  }

  return (
    <div className="json-block">
      <button
        className="json-toggle"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        aria-expanded={isOpen}
      >
        <span>{label}</span>
        <span aria-hidden="true">{isOpen ? "Hide" : "Show"}</span>
      </button>
      {isOpen ? (
        <pre>
          <code>{JSON.stringify(value, null, 2)}</code>
        </pre>
      ) : null}
    </div>
  );
}
