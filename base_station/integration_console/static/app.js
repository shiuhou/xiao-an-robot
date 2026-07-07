const expressions = ["happy", "caring", "thinking", "idle", "sad", "tired", "speaking", "surprised", "sleeping"];
let state = null;
let pending = false;
let lastPayload = null;
let hiddenLogs = false;
let visualSnapshotId = null;
let visualRequestId = null;
let cameraMtime = null;

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
  renderCameraConnection();
  renderLinks();
  renderLogs();
}

function renderCameraConnection() {
  const image = state?.media?.latest_image || {};
  const camera = state?.links?.camera || {};
  const pill = $("cameraFreshness");
  const latestImage = $("cameraLatestImage");
  const empty = $("cameraImageEmpty");
  const live = camera.done || (!!image.exists && (image.age_ms || 999999) <= 3000);
  statusPill(pill, live ? "live" : (image.exists ? "stale" : "unavailable"), live ? `LIVE · ${msAge(image.age_ms)}` : (image.exists ? `STALE · ${msAge(image.age_ms)}` : "UNAVAILABLE"));
  if (image.exists) {
    if (image.mtime !== cameraMtime) {
      cameraMtime = image.mtime;
      latestImage.src = `/api/latest-image?mtime=${encodeURIComponent(cameraMtime || Date.now())}`;
    }
    latestImage.style.display = "block";
    empty.style.display = "none";
  } else {
    latestImage.style.display = "none";
    empty.style.display = "grid";
  }
  kv("cameraKv", [
    ["文件", image.path],
    ["存在", image.exists],
    ["大小", image.size],
    ["更新时间", image.updated_at],
    ["age", msAge(image.age_ms)],
    ["状态", camera.status],
  ]);
}

function chainStatusClass(status, runMode) {
  if (!runMode) return "idle";
  if (status === "complete") return "done";
  if (status === "running") return "running";
  return "unavailable";
}

function renderChainSteps(targetId, steps = []) {
  const node = $(targetId);
  node.innerHTML = steps.map((step) => `
    <div class="chain-step ${step.ok ? "ok" : "wait"}">
      <span class="step-dot" aria-hidden="true"></span>
      <strong>${escapeHtml(step.label || "-")}</strong>
      <span>${step.ok ? "OK" : "WAIT"}</span>
    </div>
  `).join("");
}

function renderRunStatus(key, link) {
  const process = state?.processes?.[key] || {};
  const running = !!process.running;
  const status = link?.status || "idle";
  const completedOnce = !running && process.status === "exited" && process.returncode === 0 && link?.done;
  const text = running
    ? (status === "complete" ? "COMPLETE" : status.toUpperCase())
    : (completedOnce ? "DONE" : (process.status === "exited" ? "EXITED" : "OFF"));
  const switchNode = $(`${key}RunSwitch`);
  if (switchNode) switchNode.checked = running;
  statusPill(
    $(`${key}Status`),
    process.status === "exited" && !completedOnce ? "error" : chainStatusClass(status, running || completedOnce),
    text,
  );
}

function renderLinks() {
  const links = state?.links || {};
  const media = state?.media || {};
  const audio = media.latest_audio || {};
  const audioStats = media.audio_stats || {};
  const windowStats = audioStats.latest_window || {};
  const dashboard = state?.openclaw_dashboard?.dashboard || {};
  const link1 = links.link1 || {};
  const link2 = links.link2 || {};
  const link3 = links.link3 || {};
  const link1Voice = link1.voice || {};
  const link3Voice = link3.voice || {};
  const link1Phase = link1.voice_phase || {};
  const link3Phase = link3.voice_phase || {};
  const link1Audio = link1Voice.output?.event?.payload?.audio || {};
  const link3Audio = link3Voice.output?.event?.payload?.audio || {};

  renderRunStatus("link1", link1);
  renderRunStatus("link2", link2);
  renderRunStatus("link3", link3);
  renderChainSteps("link1Steps", link1.steps || []);
  renderChainSteps("link2Steps", link2.steps || []);
  renderChainSteps("link3Steps", link3.steps || []);

  kv("link1MicKv", [
    ["mic", link1Phase.label || "-"],
    ["阶段", link1Phase.detail || link1Phase.phase || "-"],
    ["runtime", state?.processes?.link1?.running ? "running" : "off"],
    ["latest output", link1Voice.ok],
    ["output age", msAge(link1Voice.age_ms)],
    ["audio", link1Audio.audio_path || "-"],
    ["sample_rate", link1Audio.sample_rate],
    ["duration_ms", link1Audio.duration_ms],
    ["状态", (link1.steps || [])[0]?.ok ? "active" : "waiting"],
  ]);
  $("link1AsrText").textContent = link1.asr_text || "-";
  $("link1OpenclawText").textContent = link1.openclaw_text || "-";
  $("link1DashboardJson").textContent = pretty({
    ok: state?.openclaw_dashboard?.ok,
    status_text: dashboard.status_text,
    mode: dashboard.mode,
    latest_reply: dashboard.latest_reply,
  });
  $("link1RobotJson").textContent = pretty(link1.robot_execution);

  kv("link3MicKv", [
    ["mic", link3Phase.label || "-"],
    ["阶段", link3Phase.detail || link3Phase.phase || "-"],
    ["runtime", state?.processes?.link3?.running ? "running" : "off"],
    ["latest output", link3Voice.ok],
    ["output age", msAge(link3Voice.age_ms)],
    ["audio", link3Audio.audio_path || "-"],
    ["sample_rate", link3Audio.sample_rate],
    ["duration_ms", link3Audio.duration_ms],
    ["状态", (link3.steps || [])[0]?.ok ? "active" : "waiting"],
  ]);
  $("link3AsrText").textContent = link3.asr_text || "-";
  $("link3FastJson").textContent = pretty(link3.fast_response);
  $("link3FollowUpText").textContent = link3.follow_up_text || "-";
}

function statusPill(node, status, text) {
  node.className = `status-pill ${status}`;
  node.textContent = text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function metricMarkup(label, value) {
  const display = value === undefined || value === null || value === "" ? "-" : String(value);
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(display)}</strong></div>`;
}

function ruleMarkup(label, value, threshold, fired) {
  return `
    <div class="gate-rule ${fired ? "fired" : "clear"}">
      <span class="rule-light" aria-hidden="true"></span>
      <span class="rule-label">${escapeHtml(label)}</span>
      <span class="rule-value">${escapeHtml(value)}</span>
      <span class="rule-threshold">${escapeHtml(threshold)}</span>
    </div>
  `;
}

function renderVisualTrace(payload) {
  const freshness = $("visualFreshness");
  const latestImage = $("visualLatestImage");
  const imageEmpty = $("visualImageEmpty");
  if (!payload?.ok) {
    statusPill(freshness, "unavailable", "UNAVAILABLE");
    latestImage.style.display = "none";
    imageEmpty.style.display = "grid";
    $("visualCvMetrics").innerHTML = metricMarkup("状态", payload?.reason || "not_found");
    $("visualGateRules").innerHTML = '<div class="empty-state">等待 Gate 数据</div>';
    statusPill($("visualGateStatus"), "unavailable", "NO DATA");
    statusPill($("visualVlmStatus"), "idle", "IDLE");
    $("visualTriggerImage").style.display = "none";
    $("visualTriggerEmpty").style.display = "grid";
    $("visualVlmDetails").innerHTML = "";
    $("visualFusion").textContent = "Fusion: -";
    return;
  }

  const trace = payload.state || {};
  const observation = trace.observation || {};
  const cv = trace.cv_sample || {};
  const gate = trace.gate || {};
  const result = gate.result || {};
  const vlm = trace.vlm || {};
  statusPill(
    freshness,
    payload.freshness === "live" ? "live" : "stale",
    `${String(payload.freshness || "stale").toUpperCase()} · ${msAge(payload.age_ms)}`,
  );
  if (trace.snapshot_id && trace.snapshot_id !== visualSnapshotId) {
    visualSnapshotId = trace.snapshot_id;
    latestImage.src = `/api/visual/latest-image?snapshot=${encodeURIComponent(visualSnapshotId)}`;
  }
  latestImage.style.display = "block";
  imageEmpty.style.display = "none";
  $("visualCvMetrics").innerHTML = [
    metricMarkup("Frame", trace.frame_id),
    metricMarkup("Face", observation.face_detected ? "detected" : "none"),
    metricMarkup("EAR", observation.ear == null ? "-" : Number(observation.ear).toFixed(3)),
    metricMarkup("MAR", observation.mar == null ? "-" : Number(observation.mar).toFixed(3)),
    metricMarkup("Emotion", cv.emotion_tag),
    metricMarkup("Confidence", cv.confidence),
    metricMarkup("Fatigue", cv.fatigue_score),
    metricMarkup("Quality", cv.observation_quality),
  ].join("");

  const force = gate.force || {};
  const fatigue = gate.fatigue || {};
  const negative = gate.single_negative || {};
  const windowRule = gate.negative_window || {};
  $("visualGateRules").innerHTML = [
    ruleMarkup("Force", force.fired ? "ON" : "OFF", "manual", !!force.fired),
    ruleMarkup("High fatigue", fatigue.value ?? "-", `>= ${fatigue.threshold ?? "-"}`, !!fatigue.fired),
    ruleMarkup("Negative", `${negative.emotion || "-"} · ${negative.confidence ?? "-"}`, `>= ${negative.confidence_threshold ?? "-"}`, !!negative.fired),
    ruleMarkup("Negative window", `${windowRule.count ?? 0}/${windowRule.count_threshold ?? "-"}`, `${windowRule.confidence_sum ?? 0}/${windowRule.confidence_sum_threshold ?? "-"}`, !!windowRule.fired),
  ].join("");
  statusPill(
    $("visualGateStatus"),
    result.should_trigger ? "triggered" : "normal",
    result.should_trigger ? `TRIGGER · ${result.reason || "unknown"}` : "NORMAL",
  );

  const vlmStatus = String(vlm.status || "idle").toLowerCase();
  statusPill($("visualVlmStatus"), vlmStatus, vlmStatus.toUpperCase());
  $("visualVlmDetails").innerHTML = [
    metricMarkup("Request", vlm.request_id),
    metricMarkup("Trigger frame", vlm.trigger_frame_id),
    metricMarkup("Reason", vlm.reason),
    metricMarkup("Latency", vlm.latency_ms == null ? "-" : `${vlm.latency_ms} ms`),
    metricMarkup("Result", vlm.result?.expression_label || vlm.result?.emotion_tag),
    metricMarkup("Confidence", vlm.result?.confidence),
  ].join("");
  const triggerImage = $("visualTriggerImage");
  const triggerEmpty = $("visualTriggerEmpty");
  if (vlm.request_id) {
    if (vlm.request_id !== visualRequestId) {
      visualRequestId = vlm.request_id;
      triggerImage.src = `/api/visual/trigger-image?request=${encodeURIComponent(visualRequestId)}`;
    }
    triggerImage.style.display = "block";
    triggerEmpty.style.display = "none";
  } else {
    triggerImage.style.display = "none";
    triggerEmpty.style.display = "grid";
  }
  const fusion = vlm.fusion || {};
  $("visualFusion").textContent = fusion.decision
    ? `Fusion · ${fusion.decision} — ${fusion.reason || ""}`
    : "Fusion: -";
}

async function refreshVisualTrace() {
  const payload = await api("/api/visual/state");
  renderVisualTrace(payload);
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
  $("refreshCameraBtn").addEventListener("click", refreshState);
  $("refreshVisualBtn").addEventListener("click", refreshVisualTrace);
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
  ["link1", "link2", "link3"].forEach((key) => {
    const node = $(`${key}RunSwitch`);
    node.addEventListener("change", async () => {
      const start = node.checked;
      const result = await post(start ? "/api/links/start" : "/api/links/stop", { link: key });
      if (!result.ok) {
        node.checked = !start;
        toast(`失败: ${result.error || "unknown"}`);
      } else {
        const oneShot = key === "link1" || key === "link3";
        toast(start ? `${key} ${oneShot ? "单次采集" : "runtime"}已启动` : `${key} runtime 已停止`);
      }
      await refreshState();
    });
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
refreshVisualTrace();
setInterval(refreshState, 1000);
setInterval(refreshVisualTrace, 1000);
