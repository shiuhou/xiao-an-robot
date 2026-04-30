#include "ws_client.h"
#include <ArduinoJson.h>

void WSClient::begin(const char* host, uint16_t port, OnControlMsg callback) {
    _onControl = callback;
    _ws.begin(host, port, "/control");
    _ws.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
        this->_onEvent(type, payload, length);
    });
    _ws.setReconnectInterval(5000);
}

void WSClient::loop() {
    _ws.loop();
    if (_connected && millis() - _lastHb > 10000) {
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
    payload["battery"]      = 100;  // TODO: read from ADC
    payload["capabilities"] = "audio,video,display,motor,servo";
    sendControl(doc);
}

void WSClient::sendHeartbeat() {
    auto doc     = buildMsg(MsgType::DEVICE_HEARTBEAT, _seq++);
    auto payload = doc["payload"].as<JsonObject>();
    payload["battery"]   = 100;   // TODO: read from ADC
    payload["wifi_rssi"] = WiFi.RSSI();
    sendControl(doc);
}

bool WSClient::isConnected() {
    return _connected;
}

void WSClient::_onEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_CONNECTED:
            _connected = true;
            Serial.println("[WSClient] Connected to base station");
            sendHello();
            break;

        case WStype_DISCONNECTED:
            _connected = false;
            Serial.println("[WSClient] Disconnected from base station");
            break;

        case WStype_TEXT: {
            JsonDocument doc;
            DeserializationError err = deserializeJson(doc, payload, length);
            if (err) {
                Serial.printf("[WSClient] JSON parse error: %s\n", err.c_str());
                break;
            }
            const char* msgType  = doc["type"] | "";
            JsonObject msgPayload = doc["payload"].as<JsonObject>();
            if (_onControl) _onControl(String(msgType), msgPayload);
            break;
        }

        case WStype_ERROR:
            Serial.println("[WSClient] WebSocket error");
            break;

        default:
            break;
    }
}
