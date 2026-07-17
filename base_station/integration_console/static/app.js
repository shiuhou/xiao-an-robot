const expressions = ["happy", "caring", "thinking", "idle", "sad", "tired", "speaking", "surprised", "sleeping"];
let state = null;
let pending = false;
let lastPayload = null;
let hiddenLogs = false;
let visualSnapshotId = null;
let visualRequestId = null;
let workVisualSnapshotId = null;
let fastVisualSnapshotId = null;
let fastVisualRequestId = null;
let cameraMtime = null;
let fast2VisualMtime = null;

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value;
}

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

function postMotion(body) {
  lastPayload = body;
  toast("运动命令已发送");
  api("/api/robot/motion", { method: "POST", body: JSON.stringify(body || {}) })
    .then((data) => {
      toast(data.ok ? "运动已确认" : `运动失败: ${data.error || data.reason || "unknown"}`);
      refreshState();
    })
    .catch((error) => {
      toast(`运动失败: ${error.message || error}`);
      refreshState();
    });
  setTimeout(refreshState, 250);
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
  const ttsRuntime = state.tts_runtime || {};
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
  $("manualRobotJson").textContent = pretty({
    selected_device_id: robot.selected_device_id,
    online: robot.online,
    last_command_ack: robot.last_command_ack,
    last_motion_completed: robot.last_motion_completed,
    last_audio_playback_done: robot.last_audio_playback_done,
    last_error: robot.last_error,
  });
  const lastAck = robot.last_command_ack?.payload || {};
  const lastPlayback = robot.last_audio_playback_done?.payload || {};
  kv("ttsRuntimeKv", [
    ["stream", ttsRuntime.control_stream_enabled],
    ["peak", ttsRuntime.target_peak],
    ["backend", ttsRuntime.backend],
    ["voice", ttsRuntime.voice],
    ["rate", ttsRuntime.rate],
    ["chunk_bytes", ttsRuntime.chunk_bytes],
    ["start_delay", ttsRuntime.start_delay_seconds],
    ["pace_ratio", ttsRuntime.pace_ratio],
    ["pcm", `${ttsRuntime.sample_rate || "-"}Hz ${ttsRuntime.channels || "-"}ch ${ttsRuntime.pcm_format || "-"}`],
    ["mode", ttsRuntime.playback_mode_expected],
  ]);
  $("ttsPlaybackJson").textContent = pretty({
    command_ack: lastAck.command_type === "audio.play_tts" ? robot.last_command_ack : null,
    playback_done: lastPlayback.command_type === "audio.play_tts" ? robot.last_audio_playback_done : null,
  });
  statusPill(
    $("manualRobotStatus"),
    robot.online ? "live" : "unavailable",
    robot.online ? "ROBOT ONLINE" : "ROBOT OFFLINE",
  );
  renderCameraConnection();
  renderWorkMode();
  renderLinks();
  renderFastDemo();
  renderLogs();
}

function renderWorkMode() {
  const work = state?.work_mode || {};
  const mode = work.state || {};
  const cards = work.cards || {};
  const systemOn = !!mode.system_enabled;
  const micRecognition = !!mode.mic_recognition_enabled;
  const cameraEnabled = !!mode.camera_capture_enabled;
  const episodeState = mode.episode_state || "idle";

  $("workModeSystemSwitch").checked = systemOn;
  $("workModeMicRecognitionSwitch").checked = micRecognition;
  $("workModeMicRecognitionSwitch").disabled = !systemOn || pending;
  $("workModeCameraSwitch").checked = cameraEnabled;
  statusPill(
    $("workModeStatus"),
    systemOn ? (episodeState === "running" ? "running" : "live") : "unavailable",
    systemOn ? (episodeState === "running" ? "RUNNING" : "WORK ON") : "OFF",
  );

  statusPill($("workSystemPill"), systemOn ? "live" : "unavailable", systemOn ? "ON" : "OFF");
  kv("workSystemKv", [
    ["状态文件", mode.persisted ? "yes" : "default"],
    ["路径", mode.path],
    ["更新时间", mode.updated_at],
    ["system_enabled", mode.system_enabled],
  ]);

  const micCard = cards.mic || {};
  statusPill(
    $("workMicPill"),
    micRecognition ? "live" : (mode.mic_device_open ? "idle" : "unavailable"),
    micRecognition ? "RECOGNIZING" : (mode.mic_device_open ? "MUTED" : "OFF"),
  );
  kv("workMicKv", [
    ["设备", mode.mic_device_open ? "open" : "closed"],
    ["送入识别", micRecognition ? "yes" : "no"],
    ["latest audio", msAge(micCard.latest_audio_age_ms)],
    ["说明", micCard.detail],
  ]);

  const cameraCard = cards.camera || {};
  statusPill(
    $("workCameraPill"),
    cameraEnabled ? (cameraCard.ok ? "live" : "stale") : "unavailable",
    cameraEnabled ? (cameraCard.ok ? "LIVE" : "WAIT") : "OFF",
  );
  kv("workCameraKv", [
    ["参与触发", cameraEnabled ? "yes" : "no"],
    ["latest image", msAge(cameraCard.latest_image_age_ms)],
    ["说明", cameraCard.detail],
  ]);

  const arbiter = cards.arbiter || {};
  statusPill(
    $("workArbiterPill"),
    episodeState === "running" ? "running" : (episodeState === "cooldown" ? "queued" : "idle"),
    String(episodeState || "IDLE").toUpperCase(),
  );
  kv("workArbiterKv", [
    ["active_chain", arbiter.active_chain || "-"],
    ["active_run_id", arbiter.active_run_id || "-"],
    ["cooldown_until", mode.cooldown_until || "-"],
    ["last", arbiter.last_episode?.status || "-"],
  ]);

  renderWorkLink("workLink1", cards.link1 || {}, cards.link1?.process || state?.processes?.work_voice || {});
  renderWorkLink("workLink2", cards.link2 || {}, cards.link2?.process || state?.processes?.link2 || {});
  renderWorkLink("workLink3", cards.link3 || {}, cards.link3?.process || state?.processes?.work_voice || {});

  renderRouteList("workLocalFastPaths", work.local_fast_paths || []);
  renderRouteList("workOpenclawPaths", work.openclaw_paths || []);
  kv("workWorkspaceKv", [
    ["workspace", work.workspace?.path],
    ["TASKS.md", work.workspace?.tasks],
    ["SCHEDULE.md", work.workspace?.schedule],
    ["NOTES.md", work.workspace?.notes],
    ["dashboard.json", work.workspace?.dashboard],
    ["local_reminders", work.workspace?.local_reminders],
  ]);
  kv("workRoutingKv", [
    ["mode", work.routing_policy?.mode],
    ["local", work.routing_policy?.local_owner],
    ["openclaw", work.routing_policy?.openclaw_owner],
    ["说明", work.routing_policy?.description],
  ]);
  $("workEpisodeJson").textContent = pretty({
    state: mode.episode_state,
    active_chain: mode.active_chain,
    active_run_id: mode.active_run_id,
    cooldown_until: mode.cooldown_until,
    last_episode: mode.last_episode,
  });
  const diagnostics = work.diagnostics || {};
  setText("workAsrText", diagnostics.asr_text || "-");
  renderWorkBrainReply();
  renderVisualDiagnostics(state?.visual || {}, {
    freshness: "workVisualFreshness",
    cvMetrics: "workVisualCvMetrics",
    gateStatus: "workVisualGateStatus",
    gateRules: "workVisualGateRules",
    vlmStatus: "workVisualVlmStatus",
    vlmDetails: "workVisualVlmDetails",
    fusion: "workVisualFusion",
  });
  renderWorkVisualFrame(state?.visual || {});
  setText("workLocalReminderJson", pretty(state?.local_fast_path_reminders || {}));
}

function renderWorkBrainReply() {
  const output = latestVoiceOutput();
  const dashboard = state?.openclaw_dashboard?.dashboard || {};
  const latestReply = dashboard.latest_reply || {};
  const route = output.route || latestReply.route || dashboard.local_fast_path?.last_route || "-";
  const reason = output.reason || latestReply.reason || dashboard.local_fast_path?.last_intent || "-";
  const source = String(route).startsWith("local_fast_path")
    ? "快速路径"
    : (route !== "-" ? "完整路径 / OpenClaw" : "-");
  const reply = (
    output.reply_text
    || output.display_text
    || output.spoken_text
    || latestReply.reply_text
    || latestReply.display_text
    || latestReply.spoken_text
    || dashboard.status_text
    || ""
  );
  kv("workBrainReplyKv", [
    ["source", source],
    ["route", route],
    ["reason", reason],
    ["updated", output.updated_at || latestReply.updated_at || dashboard.updated_at || "-"],
  ]);
  setText("workBrainReplyText", reply || "-");
}

function latestVoiceOutput() {
  const candidates = [
    state?.link_voice?.work_voice?.output,
    state?.link_voice?.link1?.output,
    state?.link_voice?.link3?.output,
    state?.fast_demo?.fast1?.voice?.output,
    state?.fast_demo?.fast3?.voice?.output,
  ];
  return candidates.find((item) => item && (item.reply_text || item.display_text || item.spoken_text || item.route)) || {};
}

function renderWorkLink(prefix, card, process) {
  const ready = !!card.ok;
  statusPill(
    $(`${prefix}Pill`),
    process.running ? "running" : (ready ? "live" : "idle"),
    process.running ? "RUNNING" : (ready ? "READY" : "WAIT"),
  );
  kv(`${prefix}Kv`, [
    ["说明", card.detail || "-"],
    ["process", process.running ? `pid ${process.pid}` : process.status || "-"],
    ["returncode", process.returncode],
    ["log", process.log_path],
  ]);
}

function renderRouteList(targetId, items) {
  const node = $(targetId);
  if (!items.length) {
    node.innerHTML = '<div class="empty-state">暂无路由</div>';
    return;
  }
  node.innerHTML = items.map((item) => `
    <div class="route-item">
      <strong>${escapeHtml(item.name || "-")}</strong>
      <span>${escapeHtml(item.owner || "-")}</span>
      <p>${escapeHtml(item.examples || item.reason || "-")}</p>
      ${item.storage ? `<code>${escapeHtml(item.storage)}</code>` : ""}
    </div>
  `).join("");
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

function refreshCameraFrame() {
  const image = state?.media?.latest_image || {};
  const latestImage = $("cameraLatestImage");
  if (!image.exists || !latestImage || latestImage.style.display === "none") {
    return;
  }
  latestImage.src = `/api/latest-image?frame=${Date.now()}`;
}

function renderFast2VisualFrame(payload) {
  const image = payload?.files?.latest_image || {};
  const latestImage = $("fast2VisualLatestImage");
  const imageEmpty = $("fast2VisualImageEmpty");
  if (!latestImage || !imageEmpty) return;
  if (image.exists) {
    if (image.mtime !== fast2VisualMtime) {
      fast2VisualMtime = image.mtime;
      latestImage.src = `/api/fast-demo/visual/latest-image?mtime=${encodeURIComponent(fast2VisualMtime || Date.now())}`;
    }
    latestImage.style.display = "block";
    imageEmpty.style.display = "none";
  } else {
    latestImage.style.display = "none";
    imageEmpty.style.display = "grid";
  }
}

function refreshFast2VisualFrame() {
  const image = state?.fast_demo?.fast2?.visual?.files?.latest_image || {};
  const latestImage = $("fast2VisualLatestImage");
  if (!image.exists || !latestImage || latestImage.style.display === "none") {
    return;
  }
  latestImage.src = `/api/fast-demo/visual/latest-image?frame=${Date.now()}`;
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
  renderLink2CareVoice(link2.openclaw_care_voice || {});

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
  renderLink2Diagnostics();

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

function renderVisualDiagnostics(payload, ids) {
  const trace = payload?.state || {};
  const observation = trace.observation || {};
  const cv = trace.cv_sample || {};
  const gate = trace.gate || {};
  const result = gate.result || {};
  const vlm = trace.vlm || {};
  const freshnessNode = ids.freshness ? $(ids.freshness) : null;
  if (!payload?.ok) {
    if (freshnessNode) statusPill(freshnessNode, "unavailable", "UNAVAILABLE");
    if (ids.cvMetrics) $(ids.cvMetrics).innerHTML = metricMarkup("状态", payload?.reason || "not_found");
    if (ids.gateRules) $(ids.gateRules).innerHTML = '<div class="empty-state">等待 Gate 数据</div>';
    if (ids.gateStatus) statusPill($(ids.gateStatus), "unavailable", "NO DATA");
    if (ids.vlmStatus) statusPill($(ids.vlmStatus), "idle", "IDLE");
    if (ids.vlmDetails) $(ids.vlmDetails).innerHTML = "";
    if (ids.fusion) $(ids.fusion).textContent = "Fusion: -";
    return { trace, observation, cv, gate, vlm };
  }

  if (freshnessNode) {
    statusPill(
      freshnessNode,
      payload.freshness === "live" ? "live" : "stale",
      `${String(payload.freshness || "stale").toUpperCase()} · ${msAge(payload.age_ms)}`,
    );
  }
  if (ids.cvMetrics) {
    $(ids.cvMetrics).innerHTML = [
      metricMarkup("Frame", trace.frame_id),
      metricMarkup("Face", observation.face_detected ? "detected" : "none"),
      metricMarkup("EAR", observation.ear == null ? "-" : Number(observation.ear).toFixed(3)),
      metricMarkup("MAR", observation.mar == null ? "-" : Number(observation.mar).toFixed(3)),
      metricMarkup("Emotion", cv.emotion_tag),
      metricMarkup("Confidence", cv.confidence),
      metricMarkup("Fatigue", cv.fatigue_score),
      metricMarkup("Quality", cv.observation_quality),
    ].join("");
  }

  const force = gate.force || {};
  const fatigue = gate.fatigue || {};
  const negative = gate.single_negative || {};
  const windowRule = gate.negative_window || {};
  if (ids.gateRules) {
    $(ids.gateRules).innerHTML = [
      ruleMarkup("Force", force.fired ? "ON" : "OFF", "manual", !!force.fired),
      ruleMarkup("High fatigue", fatigue.value ?? "-", `>= ${fatigue.threshold ?? "-"}`, !!fatigue.fired),
      ruleMarkup("Negative", `${negative.emotion || "-"} · ${negative.confidence ?? "-"}`, `>= ${negative.confidence_threshold ?? "-"}`, !!negative.fired),
      ruleMarkup("Negative window", `${windowRule.count ?? 0}/${windowRule.count_threshold ?? "-"}`, `${windowRule.confidence_sum ?? 0}/${windowRule.confidence_sum_threshold ?? "-"}`, !!windowRule.fired),
    ].join("");
  }
  if (ids.gateStatus) {
    statusPill(
      $(ids.gateStatus),
      result.should_trigger ? "triggered" : "normal",
      result.should_trigger ? `TRIGGER · ${result.reason || "unknown"}` : "NORMAL",
    );
  }

  const vlmStatus = String(vlm.status || "idle").toLowerCase();
  if (ids.vlmStatus) statusPill($(ids.vlmStatus), vlmStatus, vlmStatus.toUpperCase());
  if (ids.vlmDetails) {
    $(ids.vlmDetails).innerHTML = [
      metricMarkup("Request", vlm.request_id),
      metricMarkup("Trigger frame", vlm.trigger_frame_id),
      metricMarkup("Reason", vlm.reason),
      metricMarkup("Latency", vlm.latency_ms == null ? "-" : `${vlm.latency_ms} ms`),
      metricMarkup("Result", vlm.result?.expression_label || vlm.result?.emotion_tag),
      metricMarkup("Confidence", vlm.result?.confidence),
    ].join("");
  }
  const fusion = vlm.fusion || {};
  if (ids.fusion) {
    $(ids.fusion).textContent = fusion.decision
      ? `Fusion · ${fusion.decision} — ${fusion.reason || ""}`
      : "Fusion: -";
  }
  return { trace, observation, cv, gate, vlm };
}

function renderWorkVisualFrame(payload) {
  const latestImage = $("workVisualLatestImage");
  const imageEmpty = $("workVisualImageEmpty");
  if (!latestImage || !imageEmpty) return;
  const trace = payload?.state || {};
  if (!payload?.ok || !trace.snapshot_id) {
    latestImage.style.display = "none";
    imageEmpty.style.display = "grid";
    return;
  }
  if (trace.snapshot_id !== workVisualSnapshotId) {
    workVisualSnapshotId = trace.snapshot_id;
    latestImage.src = `/api/visual/latest-image?snapshot=${encodeURIComponent(workVisualSnapshotId)}`;
  }
  latestImage.style.display = "block";
  imageEmpty.style.display = "none";
}

function renderLink2Diagnostics() {
  const visual = state?.visual || {};
  const trace = visual.state || {};
  const observation = trace.observation || {};
  const cv = trace.cv_sample || {};
  const gate = trace.gate || {};
  const vlm = trace.vlm || {};
  const voiceCandidates = [
    state?.link_voice?.work_voice?.output,
    state?.link_voice?.link1?.output,
    state?.link_voice?.link3?.output,
    state?.fast_demo?.fast1?.voice?.output,
    state?.fast_demo?.fast3?.voice?.output,
  ];
  const latestText = voiceCandidates
    .map((item) => item?.text || item?.event?.payload?.text || "")
    .find((text) => String(text || "").trim());
  const openfacePayload = {
    freshness: visual.freshness,
    age_ms: visual.age_ms,
    frame_id: trace.frame_id,
    observation,
    cv_sample: cv,
  };
  const gatePayload = {
    gate,
    should_trigger: gate.result?.should_trigger,
    reason: gate.result?.reason,
  };
  const vlmPayload = {
    status: vlm.status,
    request_id: vlm.request_id,
    trigger_frame_id: vlm.trigger_frame_id,
    reason: vlm.reason,
    latency_ms: vlm.latency_ms,
    result: vlm.result,
    fusion: vlm.fusion,
  };
  setText("link2AsrText", latestText || "-");
  setText("link2OpenFaceJson", pretty(openfacePayload));
  setText("link2VlmTriggerJson", pretty(gatePayload));
  setText("link2VlmRuntimeJson", pretty(vlmPayload));
  setText("workAsrText", latestText || "-");
  renderVisualDiagnostics(visual, {
    freshness: "workVisualFreshness",
    cvMetrics: "workVisualCvMetrics",
    gateStatus: "workVisualGateStatus",
    gateRules: "workVisualGateRules",
    vlmStatus: "workVisualVlmStatus",
    vlmDetails: "workVisualVlmDetails",
    fusion: "workVisualFusion",
  });
  renderWorkVisualFrame(visual);
}

function renderLink2CareVoice(careVoice) {
  const text = careVoice.text || "";
  $("link2OpenclawCareVoice").textContent = text || "-";
  statusPill(
    $("link2OpenclawCareStatus"),
    text ? "done" : "unavailable",
    text ? "READY" : "NO DATA",
  );
  kv("link2OpenclawCareMeta", [
    ["source", careVoice.source || "-"],
    ["frame", careVoice.frame_id],
    ["emotion", careVoice.emotion_tag || "-"],
    ["fatigue", careVoice.fatigue_score],
    ["age", msAge(careVoice.age_ms)],
    ["reason", careVoice.reason || "-"],
  ]);
}

function renderFastDemo() {
  const fast = state?.fast_demo || {};
  const reminders = state?.fast_demo_reminders || {};
  renderStoryDemo(state?.fast_demo_story || {});
  renderDanceDemo(fast.dance || {});
  ["fast1", "fast2", "fast3"].forEach((key) => {
    renderRunStatus(key, fast[key] || {});
    renderChainSteps(`${key}Steps`, fast[key]?.steps || []);
  });
  kv("fastReminderKv", [
    ["pending", reminders.pending_count],
    ["fired", reminders.fired_count],
    ["next due", reminders.next_due_at || "-"],
    ["last processed", reminders.last_result?.processed ?? 0],
  ]);
  $("fastReminderJson").textContent = pretty({
    last_result: reminders.last_result,
    items: reminders.items,
  });

  renderFastVoiceLink("fast1", fast.fast1 || {});
  renderFastVoiceLink("fast3", fast.fast3 || {});
  const fast2 = fast.fast2 || {};
  renderFastVisualTrace(fast2.visual || {});
  $("fast2BrainText").textContent = fast2.brain_text || "-";
  $("fast2DecisionJson").textContent = pretty(fast2.decision);
  $("fast2RobotJson").textContent = pretty(fast2.robot_plan);
  $("fast2StateJson").textContent = pretty(fast2.visual?.state);
  $("fast2VisualJson").textContent = pretty({
    ok: fast2.visual?.ok,
    freshness: fast2.visual?.freshness,
    age_ms: fast2.visual?.age_ms,
    files: fast2.visual?.files,
  });
}

function renderDanceDemo(dance) {
  const voice = dance.voice || {};
  const phase = dance.voice_phase || {};
  const audio = voice.event?.payload?.audio || voice.audio || {};
  renderChainSteps("fastDanceSteps", dance.steps || []);
  statusPill(
    $("fastDanceStatus"),
    dance.status === "recording" ? "live" : (dance.keyword_matched ? "triggered" : (dance.status === "idle" ? "unavailable" : dance.status)),
    dance.status === "recording" ? "MIC ON" : (dance.keyword_matched ? "TRIGGERED" : String(dance.status || "IDLE").toUpperCase()),
  );
  kv("fastDanceMicKv", [
    ["mic", phase.label || "-"],
    ["阶段", phase.detail || phase.phase || "-"],
    ["关键词", "跳舞 / 唱歌跳舞"],
    ["命中", dance.keyword_matched ? "yes" : "no"],
    ["output age", msAge(dance.age_ms)],
    ["audio", audio.audio_path || "-"],
    ["sample_rate", audio.sample_rate],
    ["duration_ms", audio.duration_ms],
  ]);
  $("fastDanceAsrText").textContent = dance.asr_text || "-";
  $("fastDanceJson").textContent = pretty({
    keyword_matched: dance.keyword_matched,
    execution: dance.robot_execution,
    voice: dance.voice,
  });
}

function renderStoryDemo(story) {
  const node = story?.current_node || {};
  const choices = node.choices || [];
  const voice = story?.voice || {};
  const active = !!story?.active;
  const status = story?.status || "idle";
  const voiceEvent = voice.event_type || "-";
  const voiceText = voice.text || "";
  const isRecording = voiceEvent === "story.voice_recording" || voiceEvent === "voice.recording";
  statusPill(
    $("storyStatus"),
    isRecording ? "live" : (active ? "live" : (status === "completed" ? "done" : "unavailable")),
    isRecording ? "MIC ON" : (active ? "WAITING VOICE" : String(status || "IDLE").toUpperCase()),
  );
  kv("storyVoiceKv", [
    ["mic", isRecording ? "正在收音，请现在说话" : "空闲"],
    ["启动口令", active ? "说当前分支选项" : "小安，讲故事"],
    ["最近 ASR", voiceText || "-"],
    ["ASR event", voiceEvent],
    ["audio", voice.event?.payload?.audio?.audio_path || voice.audio?.audio_path || "-"],
  ]);
  $("storyNodeText").textContent = node.text || "-";
  $("storyJson").textContent = pretty({
    active: story.active,
    status: story.status,
    current_node: node.id,
    expression: node.expression,
    choices,
    history: story.history,
    voice: story.voice,
    last_execution: story.last_execution,
  });
  const choiceBox = $("storyChoiceButtons");
  choiceBox.innerHTML = "";
  if (!choices.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = active ? "请点击语音运行一次，说出你的选择" : "未开始时请点击语音运行一次，说：小安，讲故事";
    choiceBox.append(empty);
    return;
  }
  choices.forEach((choice) => {
    const hint = document.createElement("div");
    hint.className = "empty-state";
    const aliases = Array.isArray(choice.aliases) && choice.aliases.length ? `（可说：${choice.aliases.join(" / ")}）` : "";
    hint.textContent = `${choice.label || choice.id} ${aliases}`;
    choiceBox.append(hint);
  });
}

function renderFastVisualTrace(payload) {
  const freshness = $("fast2VisualFreshness");
  const triggerImage = $("fast2VisualTriggerImage");
  const triggerEmpty = $("fast2VisualTriggerEmpty");
  const image = payload?.files?.latest_image || {};
  const traceLive = !!payload?.ok && payload.freshness === "live";
  renderFast2VisualFrame(payload);
  if (!payload?.ok) {
    statusPill(
      freshness,
      image.exists ? "stale" : "unavailable",
      image.exists ? `TRACE STALE · ${msAge(image.age_ms)}` : "UNAVAILABLE",
    );
    $("fast2VisualCvMetrics").innerHTML = metricMarkup("状态", payload?.reason || "not_found");
    $("fast2VisualGateRules").innerHTML = '<div class="empty-state">等待 Gate 数据</div>';
    statusPill($("fast2VisualGateStatus"), "unavailable", "NO DATA");
    statusPill($("fast2VisualVlmStatus"), "idle", "IDLE");
    $("fast2VisualVlmDetails").innerHTML = "";
    triggerImage.style.display = "none";
    triggerEmpty.style.display = "grid";
    $("fast2VisualFusion").textContent = "Fusion: -";
    $("fast2VisualVlmJson").textContent = "{}";
    $("fast2VisualFusionJson").textContent = "{}";
    return;
  }

  const trace = payload.state || {};
  const observation = trace.observation || {};
  const cv = trace.cv_sample || {};
  const gate = trace.gate || {};
  const result = gate.result || {};
  const vlm = trace.vlm || {};
  const traceFreshness = `${String(payload.freshness || "stale").toUpperCase()} · ${msAge(payload.age_ms)}`;
  statusPill(
    freshness,
    traceLive ? "live" : "stale",
    `TRACE ${traceFreshness}`,
  );
  $("fast2VisualCvMetrics").innerHTML = [
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
  $("fast2VisualGateRules").innerHTML = [
    ruleMarkup("Force", force.fired ? "ON" : "OFF", "manual", !!force.fired),
    ruleMarkup("High fatigue", fatigue.value ?? "-", `>= ${fatigue.threshold ?? "-"}`, !!fatigue.fired),
    ruleMarkup("Negative", `${negative.emotion || "-"} · ${negative.confidence ?? "-"}`, `>= ${negative.confidence_threshold ?? "-"}`, !!negative.fired),
    ruleMarkup("Negative window", `${windowRule.count ?? 0}/${windowRule.count_threshold ?? "-"}`, `${windowRule.confidence_sum ?? 0}/${windowRule.confidence_sum_threshold ?? "-"}`, !!windowRule.fired),
  ].join("");
  statusPill(
    $("fast2VisualGateStatus"),
    result.should_trigger ? "triggered" : "normal",
    result.should_trigger ? `TRIGGER · ${result.reason || "unknown"}` : "NORMAL",
  );

  const vlmStatus = String(vlm.status || "idle").toLowerCase();
  statusPill($("fast2VisualVlmStatus"), vlmStatus, vlmStatus.toUpperCase());
  $("fast2VisualVlmDetails").innerHTML = [
    metricMarkup("Request", vlm.request_id),
    metricMarkup("Trigger frame", vlm.trigger_frame_id),
    metricMarkup("Reason", vlm.reason),
    metricMarkup("Latency", vlm.latency_ms == null ? "-" : `${vlm.latency_ms} ms`),
    metricMarkup("Result", vlm.result?.expression_label || vlm.result?.emotion_tag),
    metricMarkup("Confidence", vlm.result?.confidence),
  ].join("");
  if (vlm.request_id) {
    if (vlm.request_id !== fastVisualRequestId) {
      fastVisualRequestId = vlm.request_id;
      triggerImage.src = `/api/fast-demo/visual/trigger-image?request=${encodeURIComponent(fastVisualRequestId)}`;
    }
    triggerImage.style.display = "block";
    triggerEmpty.style.display = "none";
  } else {
    triggerImage.style.display = "none";
    triggerEmpty.style.display = "grid";
  }
  const fusion = vlm.fusion || {};
  $("fast2VisualFusion").textContent = fusion.decision
    ? `Fusion · ${fusion.decision} — ${fusion.reason || ""}`
    : "Fusion: -";
  $("fast2VisualVlmJson").textContent = pretty(vlm.result || {});
  $("fast2VisualFusionJson").textContent = pretty(fusion);
}

function renderFastVoiceLink(key, link) {
  const voice = link.voice || {};
  const phase = link.voice_phase || {};
  const audio = voice.output?.event?.payload?.audio || {};
  kv(`${key}MicKv`, [
    ["mic", phase.label || "-"],
    ["阶段", phase.detail || phase.phase || "-"],
    ["runtime", state?.processes?.[key]?.running ? "running" : "off"],
    ["latest output", voice.ok],
    ["output age", msAge(voice.age_ms)],
    ["audio", audio.audio_path || "-"],
    ["sample_rate", audio.sample_rate],
    ["duration_ms", audio.duration_ms],
  ]);
  $(`${key}AsrText`).textContent = link.asr_text || "-";
  $(`${key}BrainText`).textContent = link.brain_text || "-";
  $(`${key}DecisionJson`).textContent = pretty(link.decision);
  $(`${key}RobotJson`).textContent = pretty({
    plan: link.robot_plan,
    execution: link.robot_execution,
  });
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
  const latestImage = $("visualLatestImage");
  const imageEmpty = $("visualImageEmpty");
  const rendered = renderVisualDiagnostics(payload, {
    freshness: "visualFreshness",
    cvMetrics: "visualCvMetrics",
    gateStatus: "visualGateStatus",
    gateRules: "visualGateRules",
    vlmStatus: "visualVlmStatus",
    vlmDetails: "visualVlmDetails",
    fusion: "visualFusion",
  });
  if (!payload?.ok) {
    latestImage.style.display = "none";
    imageEmpty.style.display = "grid";
    $("visualTriggerImage").style.display = "none";
    $("visualTriggerEmpty").style.display = "grid";
    return;
  }

  const trace = rendered.trace || {};
  const vlm = rendered.vlm || {};
  if (trace.snapshot_id && trace.snapshot_id !== visualSnapshotId) {
    visualSnapshotId = trace.snapshot_id;
    latestImage.src = `/api/visual/latest-image?snapshot=${encodeURIComponent(visualSnapshotId)}`;
  }
  latestImage.style.display = "block";
  imageEmpty.style.display = "none";
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
  const durationValue = $("motionDuration").value;
  return {
    device_id: null,
    action,
    bench: $("benchMode").checked,
    params: {
      speed: Number($("motionSpeed").value || 1.0),
      distance_cm: Number($("motionDistance").value || 8),
      angle_deg: angle === undefined ? Number($("motionAngle").value || -15) : Number(angle),
      duration_ms: durationValue === "" ? undefined : Number(durationValue),
      timeout_ms: Number($("motionTimeout").value || 1200),
    },
  };
}

async function sendMotion(action, angle) {
  if (action !== "stop") {
    const bench = $("benchMode").checked ? "\n\nbench 危险 / 仅空载测试 已开启" : "";
    if (!confirm(`确认发送运动命令：${action}${bench}`)) return;
  }
  postMotion(motionBody(action, angle));
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

  $("stopAllBtn").addEventListener("click", () => postMotion(motionBody("stop")));
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
  }));
  $("sendMotionBtn").addEventListener("click", () => {
    const action = $("motionAction").value;
    sendMotion(action);
  });
  ["workModeSystemSwitch", "workModeMicRecognitionSwitch", "workModeCameraSwitch"].forEach((id) => {
    $(id).addEventListener("change", async () => {
      const body = {
        system_enabled: $("workModeSystemSwitch").checked,
        mic_recognition_enabled: $("workModeMicRecognitionSwitch").checked,
        camera_capture_enabled: $("workModeCameraSwitch").checked,
      };
      if (!body.system_enabled) body.mic_recognition_enabled = false;
      const result = await post("/api/work-mode/update", body);
      if (!result.ok) toast(`失败: ${result.error || "unknown"}`);
      await refreshState();
    });
  });
  $("workModeStartBtn").addEventListener("click", async () => {
    const result = await post("/api/work-mode/start", {
      mic_recognition_enabled: true,
      camera_capture_enabled: $("workModeCameraSwitch").checked,
    });
    $("workEpisodeJson").textContent = pretty(result);
  });
  $("workModeStopBtn").addEventListener("click", async () => {
    const result = await post("/api/work-mode/stop", {});
    $("workEpisodeJson").textContent = pretty(result);
  });
  $("agentPayloadBtn").addEventListener("click", () => {
    lastPayload = {
      transcript: $("agentText").value,
      send_to_robot: $("sendToRobotSwitch").checked,
    };
    $("agentJson").textContent = pretty(lastPayload);
  });
  $("fast2ExecuteBtn").addEventListener("click", async () => {
    if (!$("fastDemoSendRobotSwitch").checked) {
      toast("发送到机器人未开启，仅会记录跳过结果");
    } else if ($("fastDemoAllowMotionSwitch").checked && !confirm("确认执行当前视觉计划，并允许运动？")) {
      return;
    }
    const result = await post("/api/fast-demo/execute", {
      link: "fast2",
      send_to_robot: $("fastDemoSendRobotSwitch").checked,
      allow_motion: $("fastDemoAllowMotionSwitch").checked,
    });
    $("fast2RobotJson").textContent = pretty(result);
  });
  $("storyStartBtn").addEventListener("click", async () => {
    const button = $("storyStartBtn");
    const previousText = button.textContent;
    const active = !!state?.fast_demo_story?.active;
    button.textContent = active ? "正在收音，请说分支选择..." : "正在收音，请说“小安讲故事”...";
    statusPill($("storyStatus"), "live", "MIC ON");
    kv("storyVoiceKv", [
      ["mic", "正在收音，请现在说话"],
      ["启动口令", active ? "说当前分支选项" : "小安，讲故事"],
      ["最近 ASR", "-"],
      ["ASR event", "story.voice_recording"],
      ["audio", "-"],
    ]);
    try {
      const result = await post("/api/fast-demo/story/listen", {
        send_to_robot: $("fastDemoSendRobotSwitch").checked,
        allow_motion: $("fastDemoAllowMotionSwitch").checked,
      });
      $("storyJson").textContent = pretty(result);
    } finally {
      button.textContent = previousText;
    }
  });
  $("storyStopBtn").addEventListener("click", async () => {
    const result = await post("/api/fast-demo/story/stop", {});
    $("storyJson").textContent = pretty(result);
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
        toast(start ? `${key} 常驻语音 runtime 已启动` : `${key} runtime 已停止`);
      }
      await refreshState();
    });
  });
  $("fastDanceRunSwitch").addEventListener("change", async (event) => {
    if (!event.target.checked) return;
    if ($("fastDemoSendRobotSwitch").checked && !$("fastDemoAllowMotionSwitch").checked) {
      toast("请先打开允许运动，再触发唱歌跳舞");
      event.target.checked = false;
      return;
    }
    const result = await post("/api/fast-demo/dance/listen", {
      send_to_robot: $("fastDemoSendRobotSwitch").checked,
      allow_motion: $("fastDemoAllowMotionSwitch").checked,
    });
    $("fastDanceJson").textContent = pretty(result);
    event.target.checked = false;
  });
  ["fast1", "fast2", "fast3"].forEach((key) => {
    const node = $(`${key}RunSwitch`);
    node.addEventListener("change", async () => {
      const start = node.checked;
      const result = await post(start ? "/api/fast-demo/start" : "/api/fast-demo/stop", {
        link: key,
        send_to_robot: $("fastDemoSendRobotSwitch").checked,
        allow_motion: $("fastDemoAllowMotionSwitch").checked,
      });
      if (!result.ok) {
        node.checked = !start;
        toast(`失败: ${result.error || "unknown"}`);
      } else {
        const oneShot = key === "fast1" || key === "fast3";
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
setInterval(refreshCameraFrame, 200);
setInterval(refreshFast2VisualFrame, 200);
