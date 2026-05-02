#include "ws_client.h"
#include <WiFi.h>

static constexpr uint32_t HB_INTERVAL_MS  = 10000;   // heartbeat period
static constexpr uint32_t RETRY_MIN_MS    = 1000;    // initial backoff: 1 s
static constexpr uint32_t RETRY_MAX_MS    = 30000;   // backoff ceiling: 30 s

static constexpr const char* DEVICE_ID    = "xiao-an-001";
static constexpr const char* FW_VERSION   = "0.1.0";
static constexpr const char* CAPABILITIES = "audio,video,display,motor,servo";

// ── Public ───────────────────────────────────────────────────────────────────

void WSClient::begin(const char* host, uint16_t port, OnControlMsg callback) {
    _onControl = callback;
    _retryMs   = RETRY_MIN_MS;

    Serial.printf("[WSClient] Connecting to ws://%s:%u/control\n", host, port);

    _ws.begin(host, port, "/control");
    _ws.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
        _onEvent(type, payload, length);
    });
    _ws.setReconnectInterval(RETRY_MIN_MS);
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
    payload["device_id"]    = DEVICE_ID;
    payload["firmware_ver"] = FW_VERSION;
    payload["battery"]      = 100;            // TODO: read from ADC
    payload["wifi_rssi"]    = WiFi.RSSI();
    payload["capabilities"] = CAPABILITIES;
    sendControl(doc);
    Serial.println("[WSClient] Sent device.hello");
}

void WSClient::sendHeartbeat() {
    auto doc     = buildMsg(MsgType::DEVICE_HEARTBEAT, _seq++);
    auto payload = doc["payload"].as<JsonObject>();
    payload["battery"]   = 100;               // TODO: read from ADC
    payload["wifi_rssi"] = WiFi.RSSI();
    sendControl(doc);
    Serial.printf("[WSClient] Heartbeat sent (RSSI=%d dBm)\n", (int)WiFi.RSSI());
}

bool WSClient::isConnected() {
    return _connected;
}

// ── Private ──────────────────────────────────────────────────────────────────

// Arms the library reconnect timer with the current delay, then doubles it
// (capped at RETRY_MAX_MS) so subsequent failures wait longer.
// Sequence: 1 s → 2 s → 4 s → 8 s → 16 s → 30 s (ceiling).
void WSClient::_handleReconnect() {
    Serial.printf("[WSClient] Will retry in %u ms\n", _retryMs);
    _ws.setReconnectInterval(_retryMs);
    _retryMs = min(_retryMs * 2, RETRY_MAX_MS);
}

void WSClient::_onEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {

        case WStype_CONNECTED:
            _connected = true;
            _retryMs   = RETRY_MIN_MS;   // reset backoff on clean connect
            _lastHb    = millis();        // first heartbeat in 10 s from now
            Serial.printf("[WSClient] Connected (path: %s)\n", (char*)payload);
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
            Serial.printf("[WSClient] Rx: %s\n", msgType);
            if (_onControl) {
                _onControl(String(msgType), msgPayload);
            }
            break;
        }

        case WStype_ERROR:
            Serial.printf("[WSClient] WS error (len=%zu)\n", length);
            break;

        // Ping/pong handled internally by the library.
        case WStype_PING:
        case WStype_PONG:
        // Binary frames are not expected on the control channel.
        case WStype_BIN:
        default:
            break;
    }
}
