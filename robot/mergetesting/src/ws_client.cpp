#include "ws_client.h"
#include "config.h"
#include "debug_log.h"
#include <WiFi.h>
#include <memory>

namespace {

size_t base64EncodedLength(size_t inputLen) {
  return 4 * ((inputLen + 2) / 3);
}

bool base64Encode(const uint8_t* input, size_t inputLen, char* output, size_t outputCap) {
  static const char* kTable = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t outLen = base64EncodedLength(inputLen);
  if (outputCap < outLen + 1) {
    return false;
  }

  size_t i = 0;
  size_t j = 0;
  while (i + 2 < inputLen) {
    uint32_t triple = (static_cast<uint32_t>(input[i]) << 16) |
                      (static_cast<uint32_t>(input[i + 1]) << 8) |
                      static_cast<uint32_t>(input[i + 2]);
    output[j++] = kTable[(triple >> 18) & 0x3F];
    output[j++] = kTable[(triple >> 12) & 0x3F];
    output[j++] = kTable[(triple >> 6) & 0x3F];
    output[j++] = kTable[triple & 0x3F];
    i += 3;
  }

  if (i < inputLen) {
    uint32_t triple = static_cast<uint32_t>(input[i]) << 16;
    if (i + 1 < inputLen) {
      triple |= static_cast<uint32_t>(input[i + 1]) << 8;
    }

    output[j++] = kTable[(triple >> 18) & 0x3F];
    output[j++] = kTable[(triple >> 12) & 0x3F];
    if (i + 1 < inputLen) {
      output[j++] = kTable[(triple >> 6) & 0x3F];
    } else {
      output[j++] = '=';
    }
    output[j++] = '=';
  }

  output[j] = '\0';
  return true;
}

}  // namespace

void WSClient::begin(const char* host, uint16_t port, OnControlMsg callback) {
  _onControl = callback;
  _retryMs = RETRY_MIN_MS;
  _heartbeatMs = MERGETEST_HEARTBEAT_MS;
  _port = port;
  strncpy(_host, host, sizeof(_host) - 1);

  LOGI("WS", "Connecting control ws://%s:%u/control", _host, _port);
  _control.begin(_host, _port, "/control");
  _control.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
    _onControlEvent(type, payload, length);
  });
  _control.setReconnectInterval(RETRY_MIN_MS);

  _connectAll();
}

void WSClient::_connectAll() {
  if (strlen(_host) == 0) {
    return;
  }

  LOGI("WS", "Connecting video ws://%s:%u/video", _host, _port);
  _video.begin(_host, _port, "/video");
  _video.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
    _onVideoEvent(type, payload, length);
  });
  _video.setReconnectInterval(RETRY_MIN_MS);

  LOGI("WS", "Connecting audio ws://%s:%u/audio", _host, _port);
  _audio.begin(_host, _port, "/audio");
  _audio.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
    _onAudioEvent(type, payload, length);
  });
  _audio.setReconnectInterval(RETRY_MIN_MS);
}

void WSClient::loop() {
  _control.loop();
  _video.loop();
  _audio.loop();

  if (_controlConnected && (millis() - _lastHb >= _heartbeatMs)) {
    sendHeartbeat(false);
    _lastHb = millis();
  }
}

void WSClient::setVideoFps(float fps) {
  if (fps > 0.01f) {
    (void)fps;
  }
}

void WSClient::setHeartbeatIntervalMs(uint32_t ms) {
  if (ms >= 500) {
    _heartbeatMs = ms;
  }
}

void WSClient::sendControl(JsonDocument& doc) {
  if (!_controlConnected) {
    LOGW("WS", "Drop control message: not connected");
    return;
  }
  String out;
  serializeJson(doc, out);
  _control.sendTXT(out);
}

void WSClient::sendHello() {
  auto doc = buildMsg(MsgType::DEVICE_HELLO, _seq++);
  auto payload = doc["payload"].to<JsonObject>();

  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["role"] = MERGETEST_DEVICE_ROLE;
  payload["firmware"] = MERGETEST_FIRMWARE_VERSION;
  payload["fw_version"] = MERGETEST_FIRMWARE_VERSION;
  payload["battery"] = 87;
  payload["ip"] = WiFi.localIP().toString();
  payload["wifi_rssi"] = WiFi.RSSI();

  JsonArray caps = payload["capabilities"].to<JsonArray>();
  caps.add("display");
  caps.add("motion");
  caps.add("speaker");
  caps.add("camera");

  sendControl(doc);
  LOGI("WS", "Sent device.hello device_id=%s", MERGETEST_DEVICE_ID);
}

void WSClient::sendHeartbeat(bool busy) {
  auto doc = buildMsg(MsgType::DEVICE_HEARTBEAT, _seq++);
  auto payload = doc["payload"].to<JsonObject>();

  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["uptime_ms"] = millis();
  payload["uptime_sec"] = millis() / 1000;
  payload["battery"] = 87;
  payload["battery_voltage"] = 3.9;
  payload["dock"] = false;
  payload["docked"] = false;
  payload["busy"] = busy;
  payload["wifi_rssi"] = WiFi.RSSI();

  sendControl(doc);
  LOGI("WS", "Heartbeat uptime_ms=%lu busy=%s", static_cast<unsigned long>(millis()), busy ? "true" : "false");
}

void WSClient::sendStatus(const char* expression, const char* motion, const char* camera, bool docked) {
  auto doc = buildMsg(MsgType::DEVICE_STATUS, _seq++);
  auto payload = doc["payload"].to<JsonObject>();
  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["expression"] = expression ? expression : Expression::NEUTRAL;
  payload["motion"] = motion ? motion : "idle";
  payload["camera"] = camera ? camera : "cam_off";
  payload["docked"] = docked;
  payload["wifi_rssi"] = WiFi.RSSI();
  sendControl(doc);
}

void WSClient::sendCommandAck(const char* commandType, const char* status, const char* detail) {
  auto doc = buildMsg(MsgType::COMMAND_ACK, _seq++);
  auto payload = doc["payload"].to<JsonObject>();
  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["command_type"] = commandType ? commandType : "unknown";
  payload["status"] = status ? status : "ok";
  if (detail && detail[0]) {
    payload["detail"] = detail;
  }
  sendControl(doc);
  LOGI("WS", "command.ack %s -> %s", commandType ? commandType : "-", status ? status : "-");
}

void WSClient::sendMotionCompleted(const char* actionId, const char* result, const char* position, bool facingUser) {
  auto doc = buildMsg(MsgType::MOTION_COMPLETED, _seq++);
  auto payload = doc["payload"].to<JsonObject>();
  payload["action_id"] = actionId ? actionId : "";
  payload["result"] = result ? result : "success";
  auto finalState = payload["final_state"].to<JsonObject>();
  finalState["position"] = position ? position : "unknown";
  finalState["facing_user"] = facingUser;
  sendControl(doc);
}

void WSClient::sendErrorReport(const char* where, const char* message, const char* code) {
  auto doc = buildMsg(MsgType::ERROR_REPORT, _seq++);
  auto payload = doc["payload"].to<JsonObject>();
  payload["where"] = where ? where : "unknown";
  payload["code"] = code ? code : ErrorCode::UNSUPPORTED_COMMAND;
  payload["severity"] = "warning";
  payload["message"] = message ? message : "";
  sendControl(doc);
}

void WSClient::sendVideoFrameMeta(uint32_t frameId, uint16_t width, uint16_t height) {
  auto doc = buildMsg(MsgType::VIDEO_FRAME_META, _seq++);
  auto payload = doc["payload"].to<JsonObject>();
  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["format"] = "jpeg";
  payload["width"] = width;
  payload["height"] = height;
  payload["frame_id"] = frameId;
  payload["timestamp_ms"] = millis();
  sendControl(doc);
}

void WSClient::sendVideoFrameBase64(const uint8_t* jpeg, size_t len, uint32_t frameId, uint16_t width, uint16_t height) {
  if (!jpeg || len == 0) {
    return;
  }

  const size_t encodedCap = base64EncodedLength(len) + 1;
  std::unique_ptr<char[]> encoded(new (std::nothrow) char[encodedCap]);
  if (!encoded) {
    LOGE("WS", "base64 alloc failed len=%u", static_cast<unsigned>(len));
    return;
  }
  if (!base64Encode(jpeg, len, encoded.get(), encodedCap)) {
    LOGE("WS", "base64 encode failed");
    return;
  }

  JsonDocument doc;
  doc["type"] = MsgType::VIDEO_FRAME;
  doc["ts"] = static_cast<long long>(millis());
  doc["seq"] = _seq++;
  auto payload = doc["payload"].to<JsonObject>();
  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["format"] = "jpeg_base64";
  payload["width"] = width;
  payload["height"] = height;
  payload["frame_id"] = frameId;
  payload["timestamp_ms"] = millis();
  payload["data"] = encoded.get();
  sendControl(doc);
}

void WSClient::sendAsrTranscriptMock(const char* text) {
  auto doc = buildMsg(MsgType::ASR_TRANSCRIPT_MOCK, _seq++);
  auto payload = doc["payload"].to<JsonObject>();
  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["text"] = text ? text : "";
  payload["source"] = "serial_mock";
  sendControl(doc);
  LOGI("WS", "asr.transcript.mock: %s", text ? text : "");
}

void WSClient::sendAudioChunkMeta(uint32_t chunkId) {
  auto doc = buildMsg(MsgType::AUDIO_CHUNK_META, _seq++);
  auto payload = doc["payload"].to<JsonObject>();
  payload["device_id"] = MERGETEST_DEVICE_ID;
  payload["format"] = "pcm_s16le";
  payload["sample_rate"] = MERGETEST_SPEAKER_SAMPLE_RATE;
  payload["channels"] = 1;
  payload["chunk_id"] = chunkId;
  sendControl(doc);
}

bool WSClient::sendVideoBinary(const uint8_t* jpeg, size_t len, uint32_t timestampSec) {
  if (!_videoConnected || !jpeg || len == 0) {
    return false;
  }

  uint8_t header[8];
  header[0] = static_cast<uint8_t>((len >> 24) & 0xFF);
  header[1] = static_cast<uint8_t>((len >> 16) & 0xFF);
  header[2] = static_cast<uint8_t>((len >> 8) & 0xFF);
  header[3] = static_cast<uint8_t>(len & 0xFF);
  header[4] = static_cast<uint8_t>((timestampSec >> 24) & 0xFF);
  header[5] = static_cast<uint8_t>((timestampSec >> 16) & 0xFF);
  header[6] = static_cast<uint8_t>((timestampSec >> 8) & 0xFF);
  header[7] = static_cast<uint8_t>(timestampSec & 0xFF);

  _video.sendBIN(header, sizeof(header));
  _video.sendBIN(jpeg, len);
  return true;
}

bool WSClient::sendAudioBinary(const uint8_t* pcm, size_t len) {
  if (!_audioConnected || !pcm || len == 0) {
    return false;
  }
  _audio.sendBIN(pcm, len);
  return true;
}

bool WSClient::isControlConnected() const { return _controlConnected; }
bool WSClient::isVideoConnected() const { return _videoConnected; }
bool WSClient::isAudioConnected() const { return _audioConnected; }

void WSClient::_handleControlDisconnect() {
  _controlConnected = false;
  LOGW("WS", "Control disconnected, retry in %u ms", _retryMs);
  _control.setReconnectInterval(_retryMs);
  _retryMs = min(_retryMs * 2, RETRY_MAX_MS);
}

void WSClient::_onControlEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      _controlConnected = true;
      _retryMs = RETRY_MIN_MS;
      _lastHb = millis();
      LOGI("WS", "Control connected: %s", reinterpret_cast<char*>(payload));
      sendHello();
      break;

    case WStype_DISCONNECTED:
      _handleControlDisconnect();
      break;

    case WStype_TEXT: {
      JsonDocument doc;
      if (deserializeJson(doc, payload, length)) {
        LOGW("WS", "JSON parse error on control channel");
        break;
      }
      const char* msgType = doc["type"] | "";
      JsonObject msgPayload = messagePayload(doc);
      LOGI("WS", "Rx control: %s", msgType);
      if (_onControl) {
        _onControl(String(msgType), msgPayload);
      }
      break;
    }

    default:
      break;
  }
}

void WSClient::_onVideoEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      _videoConnected = true;
      LOGI("WS", "Video channel connected: %s", reinterpret_cast<char*>(payload));
      break;
    case WStype_DISCONNECTED:
      _videoConnected = false;
      LOGW("WS", "Video channel disconnected");
      break;
    default:
      (void)payload;
      (void)length;
      break;
  }
}

void WSClient::_onAudioEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      _audioConnected = true;
      LOGI("WS", "Audio channel connected: %s", reinterpret_cast<char*>(payload));
      break;
    case WStype_DISCONNECTED:
      _audioConnected = false;
      LOGW("WS", "Audio channel disconnected");
      break;
    default:
      (void)payload;
      (void)length;
      break;
  }
}
