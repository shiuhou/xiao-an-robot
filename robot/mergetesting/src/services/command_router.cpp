#include "services/command_router.h"

#include <Arduino.h>
#include <cstring>
#include "config.h"
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

void CommandRouter::loop() {
  if (_pendingPcmStream.active) {
    startPendingPcmStream();
  }
  if (_pendingPcmStreamEnd.active) {
    finishPendingPcmStream();
  }
  SpeakerPlaybackResult playback{};
  if (speaker_take_tts_playback_result(&playback)) {
    _status.audioPlaybackDone(
        playback.bytes_written,
        playback.duration_ms,
        playback.ok ? "ok" : "error");
  }
}

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
  } else if (type == MsgType::AUDIO_STREAM_END) {
    handleAudioStreamEnd(payload);
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
  const char* audioFormat = payload["audio_format"] | "";
  const uint32_t sampleRate = payload["sample_rate"] | MERGETEST_SPEAKER_SAMPLE_RATE;
  const uint8_t channels = payload["channels"] | 1;

  if (strcmp(audioFormat, "pcm_s16le") == 0 || strncmp(url, "stream://control/", 17) == 0) {
    LOGI(
        "Router",
        "audio.play_tts pcm_stream url=%s preview=%s sample_rate=%lu channels=%u",
        url,
        preview,
        static_cast<unsigned long>(sampleRate),
        static_cast<unsigned>(channels));
    _pendingPcmStream.active = true;
    _pendingPcmStream.sampleRate = sampleRate;
    _pendingPcmStream.channels = channels;
    strncpy(_pendingPcmStream.url, url, sizeof(_pendingPcmStream.url) - 1);
    _pendingPcmStream.url[sizeof(_pendingPcmStream.url) - 1] = '\0';
    strncpy(_pendingPcmStream.preview, preview, sizeof(_pendingPcmStream.preview) - 1);
    _pendingPcmStream.preview[sizeof(_pendingPcmStream.preview) - 1] = '\0';
    return;
  }

  LOGI("Router", "audio.play_tts mock tone fallback url=%s preview=%s", url, preview);

  const bool ok = speaker_play_tts_mock(preview);
  if (ok) {
    _status.sendCurrent();
    _status.ack(MsgType::AUDIO_PLAY_TTS, "accepted", "queued");
  } else {
    _status.error(
        MsgType::AUDIO_PLAY_TTS,
        "speaker not ready",
        ErrorCode::AUDIO_UNSUPPORTED);
    _status.ack(MsgType::AUDIO_PLAY_TTS, "error", "speaker_init_fail");
  }
}

void CommandRouter::startPendingPcmStream() {
  PendingPcmStream pending = _pendingPcmStream;
  _pendingPcmStream.active = false;

  LOGI(
      "Router",
      "audio.play_tts pcm_stream start url=%s preview=%s sample_rate=%lu channels=%u",
      pending.url,
      pending.preview,
      static_cast<unsigned long>(pending.sampleRate),
      static_cast<unsigned>(pending.channels));

  const bool ok = speaker_begin_pcm_stream(pending.sampleRate, pending.channels);
  if (ok) {
    _status.sendCurrent();
    _status.ack(MsgType::AUDIO_PLAY_TTS, "accepted", "pcm_stream");
  } else {
    _status.error(
        MsgType::AUDIO_PLAY_TTS,
        "speaker not ready",
        ErrorCode::AUDIO_UNSUPPORTED);
    _status.ack(MsgType::AUDIO_PLAY_TTS, "error", "speaker_init_fail");
  }
}

void CommandRouter::handleAudioStreamEnd(JsonObject payload) {
  const char* audioId = payload["audio_id"] | "";
  LOGI("Router", "audio.stream_end queued audio_id=%s", audioId);
  _pendingPcmStreamEnd.active = true;
  strncpy(_pendingPcmStreamEnd.audioId, audioId, sizeof(_pendingPcmStreamEnd.audioId) - 1);
  _pendingPcmStreamEnd.audioId[sizeof(_pendingPcmStreamEnd.audioId) - 1] = '\0';
}

void CommandRouter::finishPendingPcmStream() {
  PendingPcmStreamEnd pending = _pendingPcmStreamEnd;
  _pendingPcmStreamEnd.active = false;
  LOGI("Router", "audio.stream_end finish audio_id=%s", pending.audioId);
  speaker_end_pcm_stream();
}

void CommandRouter::handleUnsupported(const String& type) {
  LOGW("Router", "Ignoring unknown control type: %s", type.c_str());
}
