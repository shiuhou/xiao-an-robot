const expressions = ["happy", "caring", "thinking", "idle", "sad", "tired", "speaking", "surprised", "sleeping"];
let state = null;
let pending = false;
let lastPayload = null;
let hiddenLogs = false;

const $ = (id) => document.getElementById(id);

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return { ok: false, error: text || response.statusText };
  }
}

async function post(path, body) {
  pending = true;
  setPendingButtons(true);
  lastPayload = body;
  try {
    const data = await api(path, { method: "POST", body: JSON.stringify(body || {}) });
    toast(data.ok ? "已发送" : `失败: ${data.error || data.reason || "unknown"}`);
    await refreshState();
    return data;
  } finally {
    pending = false;
    setPendingButtons(false);
  }
}

function setPendingButtons(disabled) {
  document.querySelectorAll("button").forEach((button) => {
    if (button.id !== "stopAllBtn") button.disabled = disabled;
  });
}

function chip(id, ok, text, warn = false) {
  const node = $(id);
  node.textContent = text;
  node.classList.remove("ok", "bad", "warn");
  node.classList.add(ok ? "ok" : (warn ? "warn" : "bad"));
}

function kv(target, rows) {
  const node = $(target);
  node.innerHTML = "";
  rows.forEach(([key, value]) => {
    const k = document.createElement("div");
    const v = document.createElement("div");
    k.className = "k";
    v.className = "v";
    k.textContent = key;
    v.textContent = value === undefined || value === null || value === "" ? "-" : String(value);
    node.append(k, v);
  });
}

function pretty(value) {
  return JSON.stringify(value || {}, null, 2);
}

function msAge(ms) {
  if (ms === null || ms === undefined) return "-";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.round(ms / 60000)}m`;
}

async function refreshState() {
  state = await api("/api/state");
  renderState();
}

function renderState() {
  if (!state || !state.ok) return;
  const robot = state.robot || {};
  const media = state.media || {};
  const image = media.latest_image || {};
  const audio = media.latest_audio || {};
  const audioStats = media.audio_stats || {};
  const consoleState = state.console || {};
  const openclaw = state.openclaw || {};
  $("runtimePath").textContent = `runtime: ${consoleState.runtime_dir || "-"}`;
  chip("systemChip", true, `Console ${Math.round(consoleState.uptime_sec || 0)}s`);
  chip("robotChip", !!robot.online, robot.online ? `Robot ${robot.selected_device_id || "online"}` : "Robot offline");
  chip("openclawChip", !!openclaw.ok, openclaw.ok ? "OpenClaw online" : "OpenClaw offline", true);
  chip("cameraChip", !!image.exists && (image.age_ms || 999999) < 3000, image.exists ? `Camera ${msAge(image.age_ms)}` : "Camera none", true);
  chip("audioChip", !!audio.exists, audio.exists ? `Audio ${msAge(audio.age_ms)}` : "Audio none", true);
  const ack = robot.last_command_ack?.payload;
  $("ackChip").textContent = ack ? `Ack ${ack.command_type || "-"} ${ack.status || "-"}` : "Ack -";
  $("ackChip").className = "chip wide";
  if (ack) $("ackChip").classList.add(String(ack.status || "").includes("ok") || String(ack.status || "").includes("accepted") ? "ok" : "warn");

  kv("healthKv", [
    ["host:port", `${consoleState.host}:${consoleState.port}`],
    ["ws_url", consoleState.ws_url],
    ["runtime_dir", consoleState.runtime_dir],
    ["ws_state", consoleState.ws_state_exists],
    ["latest.jpg", consoleState.latest_jpg_exists],
    ["audio_stats", consoleState.audio_stats_exists],
    ["python", (consoleState.python_version || "").split(" ")[0]],
    ["OpenClaw", openclaw.ok ? "online" : openclaw.reason],
  ]);

  $("wsSummary").textContent = pretty({
    selected_device_id: robot.selected_device_id,
    online: robot.online,
    heartbeat_age: robot.last_heartbeat_age_ms,
    battery: robot.battery,
    charging: robot.charging,
    dock: robot.dock,
    wifi_rssi: robot.wifi_rssi,
    free_heap: robot.free_heap,
    reset_reason: robot.reset_reason,
    counters: state.ws_server?.state?.counters,
    last_motion_completed: robot.last_motion_completed,
    last_error: robot.last_error,
  });

  kv("imageKv", [
    ["exists", image.exists],
    ["size", image.size],
    ["updated_at", image.updated_at],
    ["age", msAge(image.age_ms)],
  ]);
  $("imageWarn").textContent = image.exists && image.age_ms > 3000 ? "latest.jpg 已超过 3 秒未更新" : "";
  updateImagePreview(image.exists);

  const windowStats = audioStats.latest_window || {};
  kv("audioKv", [
    ["latest_audio.pcm", audio.exists],
    ["pcm size", audio.size],
    ["pcm age", msAge(audio.age_ms)],
    ["chunks", audioStats.chunks],
    ["RMS", windowStats.rms],
    ["peak", windowStats.peak],
    ["DC", windowStats.dc_offset_percent],
    ["clipping", windowStats.clipping_samples],
  ]);
  $("asrJson").textContent = pretty(state.asr);
  kv("agentKv", [
    ["OpenClaw", openclaw.ok ? "online" : "offline"],
    ["url", openclaw.url],
    ["latency_ms", openclaw.latency_ms],
    ["send_to_robot", $("sendToRobotSwitch").checked],
  ]);
  $("agentJson").textContent = pretty({
    assistant_capture_result: state.asr?.assistant_capture_result,
    last_ack: robot.last_command_ack,
    last_motion_completed: robot.last_motion_completed,
    last_audio_playback_done: robot.last_audio_playback_done,
  });
  renderLogs();
}

function updateImagePreview(exists) {
  const img = $("latestImage");
  const empty = $("imageEmpty");
  if (!exists) {
    img.style.display = "none";
    empty.style.display = "grid";
    return;
  }
  img.src = `/api/latest-image?t=${Date.now()}`;
  img.style.display = "block";
  empty.style.display = "none";
}

function renderLogs() {
  if (hiddenLogs) return;
  const events = state?.recent_events || [];
  const filter = $("eventFilter").value;
  const types = [...new Set(events.map((event) => event.event_type).filter(Boolean))];
  const current = $("eventFilter").value;
  $("eventFilter").innerHTML = '<option value="">全部 event_type</option>' + types.map((type) => `<option value="${type}">${type}</option>`).join("");
  $("eventFilter").value = current;
  const filtered = filter ? events.filter((event) => event.event_type === filter) : events;
  $("logList").innerHTML = filtered.slice().reverse().map((event) => `
    <div class="log-item">
      <strong>${event.event_type || "-"}</strong> ${event.action || "-"} ${event.result || "-"} ${event.duration_ms || 0}ms
      <div>${event.timestamp || ""}</div>
      <pre>${pretty(event.payload_summary)}</pre>
    </div>
  `).join("");
}

function initExpressions() {
  $("expressionButtons").innerHTML = expressions.map((name) => `<button data-expression="${name}">${name}</button>`).join("");
  $("expressionSelect").innerHTML = expressions.map((name) => `<option value="${name}">${name}</option>`).join("");
}

function motionBody(action, angle) {
  return {
    device_id: null,
    action,
    bench: $("benchMode").checked,
    params: {
      speed: Number($("motionSpeed").value || 0.56),
      distance_cm: Number($("motionDistance").value || 8),
      timeout_ms: Number($("motionTimeout").value || 1200),
      angle_deg: angle === undefined ? undefined : Number(angle),
    },
  };
}

async function sendMotion(action, angle) {
  if (pending) return;
  if (action !== "stop") {
    const bench = $("benchMode").checked ? "\n\nbench 危险 / 仅空载测试 已开启" : "";
    if (!confirm(`确认发送运动命令：${action}${bench}`)) return;
  }
  await post("/api/robot/motion", motionBody(action, angle));
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      $(`tab-${tab.dataset.tab}`).classList.add("active");
    });
  });

  $("stopAllBtn").addEventListener("click", () => post("/api/robot/motion", motionBody("stop")));
  $("refreshBtn").addEventListener("click", refreshState);
  $("refreshImageBtn").addEventListener("click", () => updateImagePreview(state?.media?.latest_image?.exists));
  $("exportBtn").addEventListener("click", () => post("/api/logs/export", {}));
  $("exportBtn2").addEventListener("click", () => post("/api/logs/export", {}));

  document.body.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement)) return;
    if (target.dataset.expression) {
      await post("/api/robot/expression", { expression: target.dataset.expression, duration_ms: 1500, loop: false });
    }
    if (target.dataset.motion) {
      await sendMotion(target.dataset.motion, target.dataset.angle);
    }
    if (target.dataset.sound) {
      await post("/api/robot/local-sound", { sound: target.dataset.sound, volume: 0.8 });
    }
    if (target.dataset.scenario) {
      if (target.dataset.scenario !== "stop-all" && !confirm(`确认运行场景：${target.dataset.scenario}`)) return;
      const result = await post("/api/scenario/run", { scenario: target.dataset.scenario, device_id: null });
      renderScenario(result);
    }
    if (target.dataset.tool) {
      const result = await post("/api/tools/run", { tool: target.dataset.tool });
      toast(result.ok ? `${target.dataset.tool} PASS` : `${target.dataset.tool} FAIL`);
    }
  });

  $("sendExpressionBtn").addEventListener("click", () => post("/api/robot/expression", {
    expression: $("expressionSelect").value,
    duration_ms: Number($("expressionDuration").value || 1500),
    loop: false,
  }));
  $("sendCustomSoundBtn").addEventListener("click", () => post("/api/robot/local-sound", {
    sound: $("customSound").value,
    volume: 0.8,
  }));
  $("sendTtsBtn").addEventListener("click", () => post("/api/robot/tts", {
    text: $("ttsText").value,
    duration_ms: 3000,
  }));
  $("agentPayloadBtn").addEventListener("click", () => {
    lastPayload = {
      transcript: $("agentText").value,
      send_to_robot: $("sendToRobotSwitch").checked,
    };
    $("agentJson").textContent = pretty(lastPayload);
  });
  $("clearLogViewBtn").addEventListener("click", () => {
    hiddenLogs = true;
    $("logList").innerHTML = "";
  });
  $("eventFilter").addEventListener("change", () => {
    hiddenLogs = false;
    renderLogs();
  });
  $("copyPayloadBtn").addEventListener("click", async () => {
    await navigator.clipboard.writeText(pretty(lastPayload || {}));
    toast("已复制 last command payload");
  });
}

function renderScenario(result) {
  const steps = result?.steps || [];
  $("scenarioSteps").innerHTML = steps.map((step) => `
    <div class="step ${step.ok ? "ok" : "bad"}">
      <strong>${step.name}</strong> ${step.ok ? "OK" : "FAIL"} ${step.duration_ms}ms
      <pre>${pretty(step.result)}</pre>
    </div>
  `).join("");
}

initExpressions();
bindEvents();
refreshState();
setInterval(refreshState, 1000);
setInterval(() => {
  if ($("autoImageRefresh").checked && state?.media?.latest_image?.exists) {
    updateImagePreview(true);
  }
}, 1000);
