#pragma once
// Copy to config.local.h and fill local values. Do not commit config.local.h.

#define MERGETEST_WIFI_SSID "YOUR_WIFI_SSID"
#define MERGETEST_WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define MERGETEST_BASE_STATION_IP "192.168.1.100"
#define MERGETEST_BASE_STATION_PORT 8765

// Phase 1 minimal loop: /control hello + heartbeat only.
// Use mergetesting_display_only for display/motor bring-up later.
// Use mergetesting_cam_only only after /control is stable.
