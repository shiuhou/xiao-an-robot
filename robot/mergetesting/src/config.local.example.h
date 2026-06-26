#pragma once
// Copy to config.local.h and fill local values. Do not commit config.local.h.

#define MERGETEST_WIFI_SSID "YOUR_WIFI_SSID"
#define MERGETEST_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define MERGETEST_BASE_STATION_IP "192.168.1.100"
#define MERGETEST_BASE_STATION_PORT 8765
#define OTA_HOSTNAME "xiao-an-esp32"
#define OTA_PASSWORD ""

// Phase 1 minimal loop: /control hello + heartbeat only.
// Use mergetesting_display_only for Phase 1-2 USB bring-up.
// Use mergetesting_display_only_ota for Phase 1-2 OTA upload after an OTA-enabled firmware is already running.
// Use mergetesting_cam_only_ota for the OTA wireless /video smoke test.
