const clock = document.getElementById("clock");
const dateLine = document.getElementById("dateLine");
const modeChip = document.getElementById("modeChip");
const todoList = document.getElementById("todoList");
const todoCount = document.getElementById("todoCount");
const todoMore = document.getElementById("todoMore");
const scheduleList = document.getElementById("scheduleList");
const nextLine = document.getElementById("nextLine");
const replyLine = document.getElementById("replyLine");

let todayData = { todos: [], schedules: [], alarms: [] };
let dashboardState = {};

const modeLabels = {
  idle: "待命",
  listening: "聆听",
  thinking: "思考中",
  processing: "处理中",
  speaking: "说话中",
  focus: "专注",
  care: "关怀",
  running: "运行中",
  executing: "执行中",
  completed: "完成",
  failed: "异常",
  timeout: "超时",
  error: "异常",
};

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeMode(value) {
  return String(value || "idle").toLowerCase();
}

function textValue(value, fallback = "") {
  if (value == null) return fallback;
  const text = String(value).trim();
  return text || fallback;
}

function itemTitle(item, fallback = "未命名事项") {
  return textValue(item?.title || item?.text || item?.name, fallback);
}

function itemTime(item) {
  return textValue(item?.time || item?.due_time || item?.start_time, "");
}

function todoMeta(item) {
  const parts = [];
  const due = textValue(item?.due_text || item?.due || item?.time, "");
  const status = textValue(item?.status, "");
  if (due) parts.push(due);
  if (status && !["pending", "todo"].includes(status.toLowerCase())) {
    parts.push(status);
  }
  return parts.join(" · ");
}

function priorityLabel(value) {
  const priority = textValue(value, "").toLowerCase();
  if (!priority) return "";
  if (["urgent", "high", "p0", "p1"].includes(priority)) return "高";
  if (["medium", "normal", "p2"].includes(priority)) return "中";
  if (["low", "p3"].includes(priority)) return "低";
  return textValue(value);
}

function isOpenItem(item) {
  const status = textValue(item?.status || (item?.enabled === false ? "disabled" : ""), "").toLowerCase();
  return !["done", "completed", "cancelled", "disabled"].includes(status);
}

function formatNextItem(item) {
  if (item == null) return "";
  if (typeof item === "string") return textValue(item);
  if (typeof item !== "object") return textValue(item);
  const time = itemTime(item);
  const title = itemTitle(item);
  return time ? `${time} ${title}` : title;
}

function firstFallbackNext() {
  const schedules = asArray(todayData.schedules).filter(isOpenItem);
  const todos = asArray(todayData.todos).filter(isOpenItem);
  if (schedules.length > 0) return schedules[0];
  if (todos.length > 0) return todos[0];
  return null;
}

function renderMode(openclawDashboard) {
  const pipelineMode = dashboardState?.pipeline?.current_state;
  const mode = normalizeMode(openclawDashboard?.mode || pipelineMode);
  modeChip.className = `mode-chip state-${mode}`;
  modeChip.textContent = modeLabels[mode] || mode;
}

function renderTodos() {
  const todos = asArray(todayData.todos);
  const openTodos = todos.filter(isOpenItem);
  const visible = openTodos.slice(0, 4);

  todoList.replaceChildren();
  todoCount.textContent = `${openTodos.length} 项`;

  if (visible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "今天暂时没有待办";
    todoList.append(empty);
  } else {
    for (const item of visible) {
      const node = document.createElement("div");
      node.className = "todo-item";

      const dot = document.createElement("span");
      dot.className = "todo-dot";
      dot.setAttribute("aria-hidden", "true");

      const main = document.createElement("div");
      main.className = "todo-main";

      const title = document.createElement("div");
      title.className = "todo-title";
      title.textContent = itemTitle(item);

      const meta = document.createElement("div");
      meta.className = "todo-meta";
      meta.textContent = todoMeta(item);

      main.append(title, meta);

      const priority = priorityLabel(item?.priority);
      const chip = document.createElement("span");
      chip.className = `priority-chip priority-${textValue(item?.priority, "normal").toLowerCase()}`;
      chip.textContent = priority || "待办";

      node.append(dot, main, chip);
      todoList.append(node);
    }
  }

  const hidden = Math.max(0, openTodos.length - visible.length);
  todoMore.textContent = hidden > 0 ? `还有 ${hidden} 项` : "";
}

function renderSchedules() {
  const schedules = asArray(todayData.schedules).filter(isOpenItem).slice(0, 3);

  scheduleList.replaceChildren();
  if (schedules.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "今天没有更多安排";
    scheduleList.append(empty);
    return;
  }

  for (const item of schedules) {
    const node = document.createElement("div");
    node.className = "schedule-item";

    const time = document.createElement("div");
    time.className = "schedule-time";
    time.textContent = itemTime(item) || "--:--";

    const main = document.createElement("div");
    main.className = "schedule-main";

    const title = document.createElement("div");
    title.className = "schedule-title";
    title.textContent = itemTitle(item);

    const meta = document.createElement("div");
    meta.className = "schedule-meta";
    meta.textContent = textValue(item?.location || item?.status || item?.type, "");

    main.append(title, meta);
    node.append(time, main);
    scheduleList.append(node);
  }
}

function renderBottom(openclawDashboard) {
  const next = formatNextItem(openclawDashboard?.next_item || firstFallbackNext());
  const latestReply = textValue(openclawDashboard?.latest_reply?.display_text, "");
  const statusText = textValue(openclawDashboard?.status_text, "");

  nextLine.textContent = next ? `下一件事：${next}` : "下一件事：暂无";
  replyLine.textContent = latestReply || statusText || "小安正在待命。";
}

function renderDashboard() {
  const openclawDashboard = dashboardState?.openclaw_dashboard || {};
  renderMode(openclawDashboard);
  renderTodos();
  renderSchedules();
  renderBottom(openclawDashboard);
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
    dashboardState = await fetchJson("/api/dashboard/state");
  } catch (error) {
    dashboardState = {
      openclaw_dashboard: {
        mode: "error",
        status_text: "Dashboard API 暂时不可用。",
      },
    };
  }
  renderDashboard();
}

async function refreshToday() {
  try {
    todayData = await fetchJson("/api/dashboard/today");
  } catch (error) {
    todayData = { todos: [], schedules: [], alarms: [] };
  }
  renderDashboard();
}

function refreshClock() {
  const now = new Date();
  clock.textContent = now.toLocaleTimeString("zh-Hans", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  dateLine.textContent = now.toLocaleDateString("zh-Hans", {
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
