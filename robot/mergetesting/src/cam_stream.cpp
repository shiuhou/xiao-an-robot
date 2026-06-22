#include "cam_stream.h"
#include "ws_client.h"
#include "config.h"
#include "debug_log.h"

#if MERGETEST_ENABLE_CAMERA

#include "camera_ov2640_config.h"
#include "esp_camera.h"

void CamStream::begin() {
  if (_active) {
    return;
  }

  const framesize_t frameSize =
      MERGETEST_CAMERA_USE_VGA ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
  const int quality = MERGETEST_CAMERA_JPEG_QUALITY;
  const char* modeLabel = MERGETEST_CAMERA_USE_VGA ? "VGA640" : "QVGA320";

  LOGI("Cam", "Init OV2640 %s JPEG q=%d interval=%ums",
       modeLabel, quality, static_cast<unsigned>(MERGETEST_VIDEO_INTERVAL_MS));

  camera_config_t config = {};
  ov2640::fillCameraConfig(&config, frameSize, quality);

  if (esp_camera_init(&config) != ESP_OK) {
    LOGE("Cam", "esp_camera_init failed (%s)", modeLabel);
    esp_camera_deinit();
    _active = false;
    return;
  }

  sensor_t* sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_framesize(sensor, frameSize);
    sensor->set_quality(sensor, quality);
    ov2640::tuneCameraSensor(sensor);
  }

  _active = true;
  _lastCapture = 0;
  _frameId = 0;
  _captureOk = 0;
  _captureFail = 0;
  LOGI("Cam", "Camera ready %s", modeLabel);
}

void CamStream::captureLoop(WSClient& ws) {
  if (!_active || !ws.isVideoConnected()) {
    return;
  }

  const uint32_t now = millis();
  if (now - _lastCapture < MERGETEST_VIDEO_INTERVAL_MS) {
    return;
  }
  _lastCapture = now;

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb || fb->format != PIXFORMAT_JPEG) {
    ++_captureFail;
    if (fb) {
      esp_camera_fb_return(fb);
    }
    LOGE("Cam", "capture fail count=%lu", static_cast<unsigned long>(_captureFail));
    return;
  }

  ++_captureOk;
  ++_frameId;
  const uint16_t width = fb->width ? fb->width : MERGETEST_VIDEO_WIDTH;
  const uint16_t height = fb->height ? fb->height : MERGETEST_VIDEO_HEIGHT;

  ws.sendVideoFrameMeta(_frameId, width, height);

#if MERGETEST_VIDEO_BASE64_FALLBACK
  ws.sendVideoFrameBase64(fb->buf, fb->len, _frameId, width, height);
#else
  if (!ws.sendVideoBinary(fb->buf, fb->len, millis() / 1000)) {
    LOGW("Cam", "video binary send failed, fallback base64");
    ws.sendVideoFrameBase64(fb->buf, fb->len, _frameId, width, height);
  }
#endif

  LOGI("Cam", "frame #%lu %ux%u len=%u ok=%lu",
       static_cast<unsigned long>(_frameId), width, height, fb->len,
       static_cast<unsigned long>(_captureOk));
  esp_camera_fb_return(fb);
}

bool CamStream::isActive() const {
  return _active;
}

#else

void CamStream::begin() {}
void CamStream::captureLoop(WSClient&) {}
bool CamStream::isActive() const { return false; }

#endif
