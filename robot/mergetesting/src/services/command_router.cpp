#include "services/command_router.h"

#include <Arduino.h>
#include <cstring>
#include "debug_log.h"
#include "display.h"
#include "protocol.h"
#include "speaker.h"

namespace {

bool isSupportedExpression(const char* expr) {
  if (!expr || !expr[0]) {
    return false;
  }

  return strcmp(expr, Expression::NEUTRAL) == 0 ||
         strcmp(expr, Expression::IDLE) == 0 ||
         strcmp(expr, Expression::HAPPY) == 0 ||
         strcmp(expr, Expression::SAD) == 0 ||
         strcmp(expr, Expression::CARING) == 0 ||
         strcmp(expr, Expression::TIRED) == 0 ||
         strcmp(expr, Expression::THINKING) == 0 ||
         strcmp(expr, Expression::SPEAKING) == 0 ||
         strcmp(expr, Expression::LISTENING) == 0 ||
         strcmp(expr, Expression::SURPRISED) == 0 ||
         strcmp(expr, Expression::SLEEPING) == 0 ||
         strcmp(expr, Expression::ERROR) == 0;
}

bool isSupportedLocalSound(const char* sound) {
  if (!sound || !sound[0]) {
    return false;
  }

  return strcmp(sound, LocalSound::CARE_01) == 0 ||
         strcmp(sound, LocalSound::ALARM_01) == 0 ||
         strcmp(sound, LocalSound::WAKE_01) == 0 ||
         strcmp(sound, "wakeup_chime") == 0 ||
         strcmp(sound, "error_beep") == 0 ||
         strcmp(sound, "success_ding") == 0;
}

}  // namespace

CommandRouter::CommandRouter(
    WSClient& ws,
    RobotState& state,
    StatusService& status,
    MotionService& motion)
    : _ws(ws), _state(state), _status(status), _motion(motion) {}

void CommandRouter::handle(const String& type, JsonObject payload) {
  LOGI("Router", "Dispatch: %s", type.c_str());

  if (type == MsgType::SYSTEM_WELCOME) {
    handleSystemWelcome(payload);
  } else if (type == MsgType::DISPLAY_EXPRESSION) {
    handleDisplayExpression(payload);
  } else if (type == MsgType::MOTION_EXECUTE) {
    _motion.execute(payload);
  } else if (type == MsgType::AUDIO_PLAY_LOCAL) {
    handleAudioPlayLocal(payload);
  } else if (type == MsgType::AUDIO_PLAY_TTS) {
    handleAudioPlayTts(payload);
  } else if (type == MsgType::CONFIG_UPDATE) {
    _status.ack(MsgType::CONFIG_UPDATE, "ok");
  } else if (type == MsgType::SYSTEM_SHUTDOWN) {
    _status.ack(MsgType::SYSTEM_SHUTDOWN, "ok");
    delay(100);
    ESP.restart();
  } else {
    handleUnsupported(type);
  }
}

void CommandRouter::handleSystemWelcome(JsonObject payload) {
  JsonObject config = payload["config"].as<JsonObject>();
  if (!config.isNull()) {
    const int hbSec = config["heartbeat_interval_sec"] | 0;
    if (hbSec > 0) {
      _ws.setHeartbeatIntervalMs(static_cast<uint32_t>(hbSec) * 1000U);
    }

    const float videoFps = config["video_fps"] | 0.0f;
    if (videoFps > 0.0f) {
      _ws.setVideoFps(videoFps);
    }
  }

  _state.setControlConnected(true);
  display_set_connection("WS OK");
  _status.sendCurrent();
}

void CommandRouter::handleDisplayExpression(JsonObject payload) {
  const char* expr = expressionFromPayload(payload);
  const int intensity = payload["intensity"] | 5;

  if (!isSupportedExpression(expr)) {
    LOGW("Router", "Unsupported expression: %s", expr ? expr : "");
    _status.error(MsgType::DISPLAY_EXPRESSION, "unsupported expression");
    _status.ack(MsgType::DISPLAY_EXPRESSION, "error", "unsupported expression");
    return;
  }

  display_emotion(expr, intensity);
  _state.setExpression(expr);
  _status.sendCurrent();
  _status.ack(MsgType::DISPLAY_EXPRESSION, "ok");
}

void CommandRouter::handleAudioPlayLocal(JsonObject payload) {
  const char* sound = payload["sound"] | LocalSound::CARE_01;

  if (!isSupportedLocalSound(sound)) {
    LOGW("Router", "Unsupported local sound: %s", sound ? sound : "");
    _status.error(
        MsgType::AUDIO_PLAY_LOCAL,
        "unsupported local sound",
        ErrorCode::AUDIO_UNSUPPORTED);
    _status.ack(MsgType::AUDIO_PLAY_LOCAL, "error", "unsupported_sound");
    return;
  }

  const bool ok = speaker_play_local(sound);

  if (ok) {
    _status.sendCurrent();
    _status.ack(MsgType::AUDIO_PLAY_LOCAL, "ok");
  } else {
    _status.error(
        MsgType::AUDIO_PLAY_LOCAL,
        "speaker not ready",
        ErrorCode::AUDIO_UNSUPPORTED);
    _status.ack(MsgType::AUDIO_PLAY_LOCAL, "error", "speaker_init_fail");
  }
}

void CommandRouter::handleAudioPlayTts(JsonObject payload) {
  const char* url = payload["audio_url"] | "";
  const char* preview = payload["text_preview"] | payload["text"] | "";
  LOGI("Router", "audio.play_tts mock tone fallback url=%s preview=%s", url, preview);

  const bool ok = speaker_play_tts_mock(preview);
  if (ok) {
    _status.sendCurrent();
    _status.ack(MsgType::AUDIO_PLAY_TTS, "ok", "mock_tone");
  } else {
    _status.error(
        MsgType::AUDIO_PLAY_TTS,
        "speaker not ready",
        ErrorCode::AUDIO_UNSUPPORTED);
    _status.ack(MsgType::AUDIO_PLAY_TTS, "error", "speaker_init_fail");
  }
}

void CommandRouter::handleUnsupported(const String& type) {
  LOGW("Router", "Ignoring unknown control type: %s", type.c_str());
}
