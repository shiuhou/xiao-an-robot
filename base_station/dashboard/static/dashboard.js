const healthGrid = document.getElementById("healthGrid");
const pipelineFlow = document.getElementById("pipelineFlow");
const triggerList = document.getElementById("triggerList");
const todayList = document.getElementById("todayList");
const todayCount = document.getElementById("todayCount");
const clock = document.getElementById("clock");
const dateLine = document.getElementById("dateLine");
const systemMode = document.getElementById("systemMode");
const focusText = document.getElementById("focusText");
const glanceTitle = document.getElementById("glanceTitle");
const nextTime = document.getElementById("nextTime");
const nextTitle = document.getElementById("nextTitle");
const nextStatus = document.getElementById("nextStatus");

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
  ready: "就緒",
  idle: "待命",
  running: "運行",
  waiting: "等待",
  error: "錯誤",
  unknown: "未知",
  processing: "處理",
  executing: "執行",
  completed: "完成",
  acked: "確認",
  failed: "失敗",
  timeout: "超時",
};

const modeLabels = {
  idle: "待命",
  triggered: "觸發",
  processing: "處理中",
  running: "運行中",
  executing: "執行中",
  completed: "已完成",
  acked: "已確認",
  failed: "異常",
  timeout: "超時",
  error: "異常",
  unknown: "未知",
};

const voiceStatusLabels = {
  idle: "語音待命",
  listening: "正在聆聽",
  transcribing: "語音識別中",
  done: "聽到語音",
  error: "語音異常",
};

const captureStatusLabels = {
  captured: "已記錄",
  needs_clarification: "需要補充",
  failed: "記錄失敗",
  ignored: "未處理",
  routing: "正在交給 OpenClaw",
  listening: "正在聆聽",
  error: "記錄異常",
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
  if (normalized === "online") return "在線";
  if (normalized === "connected") return connectedLabel || "連上";
  if (normalized === "active") return activeLabel || "活動";
  if (normalized === "ready") return "就緒";
  if (normalized === "idle") return "待命";
  if (normalized === "offline") return "離線";
  if (normalized === "running") return "運行";
  if (normalized === "processing") return "處理";
  if (normalized === "executing") return "執行";
  return "未知";
}

function itemStatusLabel(item) {
  const value = normalizeState(item?.status || (item?.enabled ? "enabled" : "pending"));
  if (value === "done" || value === "completed") return "完成";
  if (value === "enabled") return "已啟用";
  if (value === "pending") return "待處理";
  return value;
}

function isOpenItem(item) {
  const value = normalizeState(item?.status || (item?.enabled ? "enabled" : "pending"));
  return !["done", "completed", "cancelled", "disabled"].includes(value);
}

function renderHealth(state) {
  const base = normalizeState(state?.system?.base_station, "offline");
  const robot = state?.robot?.online ? "connected" : "offline";
  const agent = normalizeState(state?.agent?.runtime, "unknown");
  const camera = normalizeState(state?.robot?.camera, "unknown");
  const audio = normalizeState(state?.robot?.audio, "unknown");

  const rows = [
    ["Base", healthLabel(base), base],
    ["Robot", healthLabel(robot), robot],
    ["Agent", healthLabel(agent), agent],
    ["Camera", healthLabel(camera, null, "活動"), camera],
    ["Audio", healthLabel(audio, null, "活動"), audio],
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
  const visible = Array.isArray(triggers) ? triggers.slice(0, 1) : [];
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
    main.textContent = `${item.time || "--:--"}  ${sourceLabels[source] || source}：${item.title || "未命名觸發"}`;

    const sub = document.createElement("div");
    sub.className = "trigger-line trigger-sub";

    const chain = document.createElement("span");
    chain.className = "trigger-chain";
    chain.textContent = item.chain || "Unknown → Dashboard";

    const statusText = document.createElement("span");
    statusText.className = "trigger-status";
    statusText.textContent = statusLabels[status] || status;

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
    .sort((a, b) => String(a.time || "").localeCompare(String(b.time || "")));
  const next = items.find(isOpenItem) || items[0];
  const previewItems = items.filter((item) => item !== next).filter(isOpenItem).slice(0, 2);

  todayList.replaceChildren();
  todayCount.textContent = String(items.length);
  if (next) {
    setText(nextTime, next.time || "--:--");
    setText(nextTitle, next.title || "未命名事項");
    setText(nextStatus, itemStatusLabel(next));
  } else {
    setText(nextTime, "--:--");
    setText(nextTitle, "今天暫無待處理事項");
    setText(nextStatus, "待命");
  }

  for (const item of previewItems) {
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
  const voice = state?.voice || {};
  const voiceStatus = normalizeState(voice.status, "idle");
  const capture = state?.assistant_capture || {};
  const captureStatus = normalizeState(capture.status, "idle");
  systemMode.className = `mode-pill state-${mode}`;
  systemMode.textContent = modeLabels[mode] || mode;

  if (["captured", "needs_clarification", "failed", "error", "routing", "listening"].includes(captureStatus)) {
    glanceTitle.textContent = captureStatusLabels[captureStatus] || "語音記錄";
    const captureData = capture.capture || {};
    const summary = captureData.title || captureData.content || captureData.summary || capture.reply_text || capture.transcript;
    focusText.textContent = capture.error || summary || "等待 OpenClaw 返回記錄結果。";
    systemMode.className = `mode-pill state-${captureStatus === "captured" ? "completed" : captureStatus === "needs_clarification" ? "processing" : captureStatus}`;
    systemMode.textContent = captureStatusLabels[captureStatus] || "語音記錄";
  } else if (voiceStatus === "done" && voice.transcript) {
    glanceTitle.textContent = voiceStatusLabels.done;
    focusText.textContent = voice.transcript;
    systemMode.className = "mode-pill state-completed";
    systemMode.textContent = "語音完成";
  } else if (voiceStatus === "listening" || voiceStatus === "transcribing") {
    glanceTitle.textContent = voiceStatusLabels[voiceStatus];
    focusText.textContent = voice.audio_device ? `輸入設備：${voice.audio_device}` : "等待麥克風輸入。";
    systemMode.className = "mode-pill state-processing";
    systemMode.textContent = voiceStatusLabels[voiceStatus];
  } else if (voiceStatus === "error" && voice.error) {
    glanceTitle.textContent = voiceStatusLabels.error;
    focusText.textContent = voice.error;
    systemMode.className = "mode-pill state-error";
    systemMode.textContent = "語音異常";
  } else {
    const trigger = state?.pipeline?.current_trigger;
    if (trigger) {
      glanceTitle.textContent = mode === "executing" ? "正在執行" : "已觸發";
      focusText.textContent = `${trigger} 正在經過 Base、Agent 與 Robot。`;
    } else if (mode === "idle") {
      glanceTitle.textContent = "待命中";
      focusText.textContent = "等待日程、鬧鐘、語音、情緒或手動測試觸發。";
    } else if (["failed", "timeout", "error"].includes(mode)) {
      glanceTitle.textContent = "需要檢查";
      focusText.textContent = "鏈路出現異常，請查看 Base、Robot、Agent 狀態。";
    } else {
      glanceTitle.textContent = modeLabels[mode] || "運行中";
      focusText.textContent = "事件正在處理，請留意 Robot 動作或語音回應。";
    }
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
    systemMode.className = "mode-pill state-offline";
    glanceTitle.textContent = "Dashboard 離線";
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
