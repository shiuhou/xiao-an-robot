#pragma once
// ws_client.h — /control + /video + /audio WebSocket 客户端

#include <Arduino.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <functional>
#include "protocol.h"

typedef std::function<void(const String& type, JsonObject payload)> OnControlMsg;

class WSClient {
public:
  void begin(const char* host, uint16_t port, OnControlMsg callback);
  void loop();

  void sendControl(JsonDocument& doc);
  void sendHello();
  void sendHeartbeat(bool busy);
  void sendStatus(const char* expression, const char* motion, const char* camera, bool docked);
  void sendCommandAck(const char* commandType, const char* status, const char* detail = nullptr);
  void sendMotionCompleted(const char* actionId, const char* result, const char* position, bool facingUser);
  void sendErrorReport(const char* where, const char* message, const char* code = ErrorCode::UNSUPPORTED_COMMAND);
  void sendVideoFrameMeta(uint32_t frameId, uint16_t width, uint16_t height);
  void sendVideoFrameBase64(const uint8_t* jpeg, size_t len, uint32_t frameId, uint16_t width, uint16_t height);
  void sendAsrTranscriptMock(const char* text);
  void sendAudioChunkMeta(uint32_t chunkId);

  bool sendVideoBinary(const uint8_t* jpeg, size_t len, uint32_t timestampSec);
  bool sendAudioBinary(const uint8_t* pcm, size_t len);

  bool isControlConnected() const;
  bool isVideoConnected() const;
  bool isAudioConnected() const;

  void setVideoFps(float fps);
  void setHeartbeatIntervalMs(uint32_t ms);

private:
  WebSocketsClient _control;
  WebSocketsClient _video;
  WebSocketsClient _audio;

  OnControlMsg _onControl;
  uint32_t _seq = 0;
  uint32_t _lastHb = 0;
  uint32_t _retryMs = 1000;
  uint32_t _heartbeatMs = 2000;
  bool _controlConnected = false;
  bool _videoConnected = false;
  bool _audioConnected = false;
  char _host[64] = {};
  uint16_t _port = 8765;

  static constexpr uint32_t RETRY_MIN_MS = 1000;
  static constexpr uint32_t RETRY_MAX_MS = 30000;

  void _connectAll();
  void _onControlEvent(WStype_t type, uint8_t* payload, size_t length);
  void _onVideoEvent(WStype_t type, uint8_t* payload, size_t length);
  void _onAudioEvent(WStype_t type, uint8_t* payload, size_t length);
  void _handleControlDisconnect();
};
