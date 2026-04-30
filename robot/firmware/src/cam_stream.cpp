#include "cam_stream.h"

void CamStream::begin() {
    // TODO: initialize ESP32 camera driver (esp_camera_init)
    // TODO: set resolution QVGA (320x240) for bandwidth
}

void CamStream::captureLoop() {
    // TODO: every CAPTURE_INTERVAL_MS, capture JPEG frame
    // TODO: send via WebSocket /video channel with 8-byte header (length + timestamp)
}

bool CamStream::isActive() {
    return _active;
}
