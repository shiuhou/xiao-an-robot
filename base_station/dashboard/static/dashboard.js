const healthGrid = document.getElementById("healthGrid");
const pipelineFlow = document.getElementById("pipelineFlow");
const triggerList = document.getElementById("triggerList");
const todayList = document.getElementById("todayList");
const todayCount = document.getElementById("todayCount");
const clock = document.getElementById("clock");
const dateLine = document.getElementById("dateLine");
const systemMode = document.getElementById("systemMode");
const focusText = document.getElementById("focusText");
const imageSignal = document.getElementById("imageSignal");
const audioSignal = document.getElementById("audioSignal");
const modeSignal = document.getElementById("modeSignal");

const sourceLabels = {
  schedule: "日程",
  todo: "待辦",
  alarm: "鬧鐘",
  emotion: "情緒",
  voice: "語音",
  manual: "手動",
  agent: "Agent",
  system: "系統",
};

const statusLabels = {
  idle: "未觸發",
  triggered: "已觸發",
  processing: "處理中",
  executing: "Robot 執行中",
  acked: "Robot 已確認",
  completed: "完成",
  failed: "失敗",
  timeout: "超時",
};

const pipelineLabels = {
  ready: "READY",
  idle: "IDLE",
  running: "RUNNING",
  waiting: "WAITING",
  error: "ERROR",
  unknown: "UNKNOWN",
  processing: "RUNNING",
  executing: "RUNNING",
  completed: "READY",
  acked: "READY",
  failed: "ERROR",
  timeout: "ERROR",
};

function normalizeState(value, fallback = "unknown") {
  return String(value || fallback).toLowerCase();
}

function chip(label, state) {
  const normalized = normalizeState(state);
  const node = document.createElement("span");
  node.className = `status-chip state-${normalized}`;

  const dot = document.createElement("span");
  dot.className = "dot";
  dot.setAttribute("aria-hidden", "true");

  const text = document.createElement("span");
  text.textContent = label;

  node.append(dot, text);
  return node;
}

function setText(node, value) {
  node.textContent = value == null || value === "" ? "Unknown" : String(value);
}

function healthLabel(state, connectedLabel, activeLabel) {
  const normalized = normalizeState(state);
  if (normalized === "online") return "Online";
  if (normalized === "connected") return connectedLabel || "Connected";
  if (normalized === "active") return activeLabel || "Active";
  if (normalized === "ready") return "Ready";
  if (normalized === "idle") return "Idle";
  if (normalized === "offline") return "Offline";
  return "Unknown";
}

function renderHealth(state) {
  const base = normalizeState(state?.system?.base_station, "offline");
  const robot = state?.robot?.online ? "connected" : "offline";
  const agent = normalizeState(state?.agent?.runtime, "unknown");
  const camera = normalizeState(state?.robot?.camera, "unknown");
  const audio = normalizeState(state?.robot?.audio, "unknown");

  const rows = [
    ["Base Station", healthLabel(base), base],
    ["Robot", healthLabel(robot), robot],
    ["Agent", healthLabel(agent), agent],
    ["Camera", healthLabel(camera, null, "Active"), camera],
    ["Audio", healthLabel(audio, null, "Active"), audio],
  ];

  healthGrid.replaceChildren();
  for (const [label, value, stateName] of rows) {
    const row = document.createElement("div");
    row.className = "health-row";

    const left = document.createElement("span");
    left.className = "health-label";
    left.textContent = label;

    row.append(left, chip(value, stateName));
    healthGrid.append(row);
  }
}

function renderPipeline(pipeline) {
  const steps = [
    ["Robot", pipeline?.robot],
    ["Base", pipeline?.base_station],
    ["Agent", pipeline?.agent],
    ["Action", pipeline?.action],
  ];

  pipelineFlow.replaceChildren();
  for (const [name, state] of steps) {
    const normalized = normalizeState(state);
    const node = document.createElement("div");
    node.className = `pipeline-step state-${normalized}`;

    const dot = document.createElement("span");
    dot.className = "dot";
    dot.setAttribute("aria-hidden", "true");

    const nameNode = document.createElement("div");
    nameNode.className = "pipeline-name";
    nameNode.textContent = name;

    const statusNode = document.createElement("div");
    statusNode.className = "pipeline-status";
    statusNode.textContent = pipelineLabels[normalized] || normalized.toUpperCase();

    node.append(dot, nameNode, statusNode);
    pipelineFlow.append(node);
  }
}

function renderTriggers(triggers) {
  triggerList.replaceChildren();
  const visible = Array.isArray(triggers) ? triggers.slice(0, 3) : [];
  if (visible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-triggers";
    empty.textContent = "暫無觸發，小安正在待命";
    triggerList.append(empty);
    return;
  }

  for (const item of visible) {
    const status = normalizeState(item.status, "idle");
    const source = normalizeState(item.source, "system");
    const node = document.createElement("div");
    node.className = `trigger-item state-${status}`;

    const main = document.createElement("div");
    main.className = "trigger-line trigger-main";
    main.textContent = `${item.time || "--:--"}  ${sourceLabels[source] || source}  ${item.title || "未命名觸發"}`;

    const sub = document.createElement("div");
    sub.className = "trigger-line trigger-sub";

    const chain = document.createElement("span");
    chain.className = "trigger-chain";
    chain.textContent = item.chain || "Unknown → Dashboard";

    const statusText = document.createElement("span");
    statusText.className = "trigger-status";
    statusText.textContent = `狀態：${statusLabels[status] || status}`;

    sub.append(chain, statusText);
    node.append(main, sub);
    triggerList.append(node);
  }
}

function renderToday(data) {
  const items = [
    ...(Array.isArray(data?.schedules) ? data.schedules : []),
    ...(Array.isArray(data?.todos) ? data.todos : []),
    ...(Array.isArray(data?.alarms) ? data.alarms : []),
  ]
    .slice(0, 6)
    .sort((a, b) => String(a.time || "").localeCompare(String(b.time || "")));

  todayList.replaceChildren();
  todayCount.textContent = String(items.length);

  for (const item of items) {
    const node = document.createElement("div");
    node.className = "today-item";

    const time = document.createElement("span");
    time.className = "today-time";
    time.textContent = item.time || "--:--";

    const title = document.createElement("span");
    title.className = "today-title";
    title.textContent = item.title || "未命名事項";

    const status = document.createElement("span");
    status.className = "today-status";
    status.textContent = item.status || (item.enabled ? "enabled" : "pending");

    node.append(time, title, status);
    todayList.append(node);
  }
}

function renderState(state) {
  renderHealth(state);
  renderPipeline(state.pipeline || {});
  renderTriggers(state.triggers || []);

  const mode = normalizeState(state?.pipeline?.current_state, "idle");
  systemMode.textContent = mode === "idle" ? "待命" : mode.toUpperCase();
  setText(imageSignal, healthLabel(state?.robot?.camera));
  setText(audioSignal, healthLabel(state?.robot?.audio));
  setText(modeSignal, mode.toUpperCase());

  const trigger = state?.pipeline?.current_trigger;
  if (trigger) {
    focusText.textContent = `最近由 ${trigger} 觸發，鏈路狀態正在更新。`;
  } else if (mode === "idle") {
    focusText.textContent = "小安正在待命，等待日程、鬧鐘、語音、情緒或手動測試觸發。";
  } else {
    focusText.textContent = "鏈路事件已觸發，正在經過 Base Station、Agent 與 Robot 執行節點。";
  }
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function refreshState() {
  try {
    const state = await fetchJson("/api/dashboard/state");
    renderState(state);
  } catch (error) {
    renderHealth({
      system: { base_station: "offline" },
      robot: { online: false, camera: "unknown", audio: "unknown" },
      agent: { runtime: "unknown" },
    });
    renderPipeline({
      robot: "unknown",
      base_station: "error",
      agent: "unknown",
      action: "waiting",
    });
    renderTriggers([]);
    systemMode.textContent = "離線";
    focusText.textContent = "Dashboard API 暫時不可用。";
  }
}

async function refreshToday() {
  try {
    renderToday(await fetchJson("/api/dashboard/today"));
  } catch (error) {
    renderToday({ schedules: [], todos: [], alarms: [] });
  }
}

function refreshClock() {
  const now = new Date();
  clock.textContent = now.toLocaleTimeString("zh-Hant", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  dateLine.textContent = now.toLocaleDateString("zh-Hant", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
}

refreshClock();
refreshState();
refreshToday();
setInterval(refreshClock, 1000);
setInterval(refreshState, 5000);
setInterval(refreshToday, 45000);
