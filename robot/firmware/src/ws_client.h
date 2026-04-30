#pragma once
// ws_client.h
// WebSocket client for ESP32-S3
// Connects to base station, handles all 3 channels
// Author: 施宇灏

#include <Arduino.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include "protocol.h"

// Callback type for incoming control messages
typedef std::function<void(const String& type, JsonObject payload)> OnControlMsg;

class WSClient {
public:
    void begin(const char* host, uint16_t port, OnControlMsg callback);
    void loop();
    void sendControl(JsonDocument& doc);
    void sendHello();
    void sendHeartbeat();
    bool isConnected();

private:
    WebSocketsClient _ws;
    OnControlMsg     _onControl;
    uint32_t         _seq       = 0;
    uint32_t         _lastHb    = 0;
    uint32_t         _retryMs   = 1000;
    bool             _connected = false;

    void _onEvent(WStype_t type, uint8_t* payload, size_t length);
    void _handleReconnect();
};
