#pragma once

#include <Arduino.h>
#include <functional>

class WSClient;

typedef std::function<void(const uint8_t* jpeg, size_t len, uint16_t width, uint16_t height, uint32_t frameId)> VideoFrameHandler;

class CamStream {
public:
  void begin();
  void captureLoop(WSClient& ws);
  bool isActive() const;

private:
  bool _active = false;
  uint32_t _lastCapture = 0;
  uint32_t _frameId = 0;
  uint32_t _captureOk = 0;
  uint32_t _captureFail = 0;
};
