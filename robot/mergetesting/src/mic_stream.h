#pragma once
// mic_stream.h — INMP441 PCM 采集（提取自 voice_recognition_test.cpp）

#include <Arduino.h>

class WSClient;

class MicStream {
public:
  void begin();
  void streamLoop(WSClient& ws);
  bool isActive() const;

private:
  bool _active = false;
  uint32_t _chunkId = 0;
  uint32_t _lastSendMs = 0;
};
