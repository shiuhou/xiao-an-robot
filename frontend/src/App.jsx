import React, { useState } from "react";

import ChatPage from "./components/ChatPage";
import MemoryPanel from "./components/MemoryPanel";
import RemindersPanel from "./components/RemindersPanel";
import Sidebar from "./components/Sidebar";
import StatusDashboard from "./components/StatusDashboard";
import TasksPanel from "./components/TasksPanel";

const NAV_ITEMS = [
  { id: "status", label: "Status" },
  { id: "chat", label: "Chat" },
  { id: "tasks", label: "Tasks" },
  { id: "reminders", label: "Reminders" },
  { id: "memory", label: "Memory" },
  { id: "tools", label: "Tools" },
];

function ComingSoon({ label }) {
  return (
    <section className="coming-soon" aria-labelledby="coming-soon-title">
      <p className="section-kicker">Xiao An Frontend MVP</p>
      <h1 id="coming-soon-title">{label}</h1>
      <p>This workspace will be available in a later step.</p>
    </section>
  );
}

export default function App() {
  const [activePage, setActivePage] = useState("status");
  const activeItem =
    NAV_ITEMS.find((item) => item.id === activePage) ?? NAV_ITEMS[0];

  return (
    <div className="app-shell">
      <Sidebar
        items={NAV_ITEMS}
        activePage={activePage}
        onNavigate={setActivePage}
      />

      <main className="main-content">
        {activePage === "status" && <StatusDashboard />}
        {activePage === "chat" && <ChatPage />}
        {activePage === "tasks" && <TasksPanel />}
        {activePage === "reminders" && <RemindersPanel />}
        {activePage === "memory" && <MemoryPanel />}
        {!["status", "chat", "tasks", "reminders", "memory"].includes(
          activePage,
        ) && (
          <ComingSoon label={activeItem.label} />
        )}
      </main>
    </div>
  );
}
