#include "ws_client.h"
#include <WiFi.h>

static constexpr uint32_t HB_INTERVAL_MS = 10000;   // heartbeat every 10 s
static constexpr uint32_t RETRY_MAX_MS   = 30000;   // backoff ceiling

// ── Public ───────────────────────────────────────────────────────────────────

void WSClient::begin(const char* host, uint16_t port, OnControlMsg callback) {
    _onControl = callback;
    _ws.begin(host, port, "/control");
    _ws.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
        this->_onEvent(type, payload, length);
    });
    // Start with the initial backoff value; reset to 1 s after each clean connect.
    _ws.setReconnectInterval(_retryMs);
}

void WSClient::loop() {
    _ws.loop();
    if (_connected && (millis() - _lastHb >= HB_INTERVAL_MS)) {
        sendHeartbeat();
        _lastHb = millis();
    }
}

void WSClient::sendControl(JsonDocument& doc) {
    String out;
    serializeJson(doc, out);
    _ws.sendTXT(out);
}

void WSClient::sendHello() {
    auto doc     = buildMsg(MsgType::DEVICE_HELLO, _seq++);
    auto payload = doc["payload"].as<JsonObject>();
    payload["device_id"]    = "xiao-an-001";
    payload["firmware_ver"] = "0.1.0";
    payload["battery"]      = 100;   // TODO: read from ADC
    payload["capabilities"] = "audio,video,display,motor,servo";
    sendControl(doc);
}

void WSClient::sendHeartbeat() {
    auto doc     = buildMsg(MsgType::DEVICE_HEARTBEAT, _seq++);
    auto payload = doc["payload"].as<JsonObject>();
    payload["battery"]   = 100;        // TODO: read from ADC
    payload["wifi_rssi"] = WiFi.RSSI();
    sendControl(doc);
}

bool WSClient::isConnected() {
    return _connected;
}

// ── Private ──────────────────────────────────────────────────────────────────

// Called on disconnect to arm the library's reconnect timer with the current
// backoff value, then double it (capped at RETRY_MAX_MS) for next time.
void WSClient::_handleReconnect() {
    Serial.printf("[WSClient] Reconnecting in %u ms\n", _retryMs);
    _ws.setReconnectInterval(_retryMs);
    _retryMs = min(_retryMs * 2, RETRY_MAX_MS);
}

void WSClient::_onEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {

        case WStype_CONNECTED:
            _connected = true;
            _retryMs   = 1000;          // reset backoff on clean connect
            _lastHb    = millis();      // start heartbeat timer from now
            _ws.setReconnectInterval(1000);
            sendHello();
            break;

        case WStype_DISCONNECTED:
            _connected = false;
            Serial.println("[WSClient] Disconnected from base station");
            _handleReconnect();
            break;

        case WStype_TEXT: {
            JsonDocument doc;
            DeserializationError err = deserializeJson(doc, payload, length);
            if (err) {
                Serial.printf("[WSClient] JSON parse error: %s\n", err.c_str());
                break;
            }
            const char* msgType    = doc["type"] | "";
            JsonObject  msgPayload = doc["payload"].as<JsonObject>();
            if (_onControl) _onControl(String(msgType), msgPayload);
            break;
        }

        case WStype_ERROR:
            Serial.println("[WSClient] WebSocket error");
            break;

        // Ping/pong handled internally by the library; nothing to do here.
        case WStype_PING:
        case WStype_PONG:
            break;

        default:
            break;
    }
}
