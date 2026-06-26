import React from "react";

export default function Sidebar({ items, activePage, onNavigate }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark" aria-hidden="true">
          XA
        </span>
        <div>
          <p className="brand-name">Xiao An</p>
          <p className="brand-caption">Runtime Debug</p>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main navigation">
        {items.map((item) => {
          const isActive = item.id === activePage;
          return (
            <button
              className={`nav-item${isActive ? " active" : ""}`}
              type="button"
              key={item.id}
              onClick={() => onNavigate(item.id)}
              aria-current={isActive ? "page" : undefined}
            >
              <span className="nav-indicator" aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <p className="sidebar-footer">OpenClaw bridge console</p>
    </aside>
  );
}
