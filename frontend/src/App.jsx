import React, { useState } from "react";

import ChatPage from "./components/ChatPage";
import EmotionTimelinePanel from "./components/EmotionTimelinePanel";
import RobotDebugPanel from "./components/RobotDebugPanel";
import RuntimeLogsPanel from "./components/RuntimeLogsPanel";
import Sidebar from "./components/Sidebar";
import StatusDashboard from "./components/StatusDashboard";

const NAV_ITEMS = [
  { id: "status", label: "Status" },
  { id: "chat", label: "Chat" },
  { id: "robot-debug", label: "Robot Debug" },
  { id: "emotion-timeline", label: "Emotion Timeline" },
  { id: "runtime-logs", label: "Runtime Logs" },
];

function ComingSoon({ label }) {
  return (
    <section className="coming-soon" aria-labelledby="coming-soon-title">
      <p className="section-kicker">Xiao An Runtime Debug</p>
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
        {activePage === "robot-debug" && <RobotDebugPanel />}
        {activePage === "emotion-timeline" && <EmotionTimelinePanel />}
        {activePage === "runtime-logs" && <RuntimeLogsPanel />}
        {![
          "status",
          "chat",
          "robot-debug",
          "emotion-timeline",
          "runtime-logs",
        ].includes(
          activePage,
        ) && (
          <ComingSoon label={activeItem.label} />
        )}
      </main>
    </div>
  );
}
