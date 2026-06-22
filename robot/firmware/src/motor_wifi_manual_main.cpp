#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>

#include "motor_ctrl.h"

namespace {

constexpr const char* WIFI_SSID = "XiaoAn-Motor";
constexpr const char* WIFI_PASSWORD = "12345678";

constexpr int MOTOR_SPEED_MIN = 40;
constexpr int MOTOR_SPEED_MAX = 180;
constexpr int MOTOR_SPEED_STEP = 10;
constexpr int MOTOR_SPEED_DEFAULT = 120;
constexpr uint32_t MOTOR_DEADMAN_MS = 350;

WebServer server(80);
MotorController motor;

int motorSpeed = MOTOR_SPEED_DEFAULT;
uint32_t motorHoldUntilMs = 0;
bool motorActive = false;
char lastCommand = 'x';

const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
  <title>Xiao-An Motor</title>
  <style>
    * { box-sizing: border-box; touch-action: none; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101418;
      color: #f3f5f7;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    main { width: min(420px, 94vw); }
    h1 { font-size: 22px; margin: 0 0 14px; }
    .status {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 16px;
      color: #b8c0c8;
      font-size: 14px;
    }
    .pad {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    button {
      border: 0;
      border-radius: 8px;
      min-height: 82px;
      font-size: 26px;
      font-weight: 700;
      color: #f7fafc;
      background: #2f3944;
      box-shadow: inset 0 -3px 0 rgba(0,0,0,.25);
    }
    button:active, button.active { background: #2f7dd1; }
    .stop { background: #a12f2f; }
    .small { min-height: 54px; font-size: 18px; }
    .empty { visibility: hidden; }
  </style>
</head>
<body>
<main>
  <h1>Xiao-An Motor</h1>
  <div class="status">
    <div>Command: <span id="cmd">x</span></div>
    <div>Speed: <span id="speed">120</span></div>
  </div>
  <section class="pad">
    <button class="empty"></button>
    <button data-cmd="w">W</button>
    <button class="empty"></button>
    <button data-cmd="a">A</button>
    <button data-cmd="x" class="stop">X</button>
    <button data-cmd="d">D</button>
    <button data-cmd="-">-</button>
    <button data-cmd="s">S</button>
    <button data-cmd="+">+</button>
  </section>
</main>
<script>
const cmdEl = document.getElementById("cmd");
const speedEl = document.getElementById("speed");
let timer = null;
let activeButton = null;

async function send(c) {
  try {
    const response = await fetch(`/cmd?c=${encodeURIComponent(c)}`, { cache: "no-store" });
    const data = await response.json();
    cmdEl.textContent = data.command;
    speedEl.textContent = data.speed;
  } catch (error) {
    cmdEl.textContent = "offline";
  }
}

function start(button) {
  stop(false);
  activeButton = button;
  activeButton.classList.add("active");
  const c = button.dataset.cmd;
  send(c);
  if ("wasd".includes(c)) {
    timer = setInterval(() => send(c), 120);
  }
}

function stop(sendStop = true) {
  if (timer) clearInterval(timer);
  timer = null;
  if (activeButton) activeButton.classList.remove("active");
  activeButton = null;
  if (sendStop) send("x");
}

document.querySelectorAll("button[data-cmd]").forEach((button) => {
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    start(button);
  });
  button.addEventListener("pointerup", () => stop(true));
  button.addEventListener("pointercancel", () => stop(true));
  button.addEventListener("pointerleave", () => stop(true));
});

window.addEventListener("keydown", (event) => {
  const c = event.key.toLowerCase();
  if ("wasdx+-=".includes(c)) send(c === "=" ? "+" : c);
});
window.addEventListener("keyup", (event) => {
  if ("wasd".includes(event.key.toLowerCase())) send("x");
});

send("x");
</script>
</body>
</html>
)HTML";

void holdMotorPinsLowBeforeSerial() {
    const int8_t motorPins[] = {
        PIN_MOTOR_L_IN1,
        PIN_MOTOR_L_IN2,
        PIN_MOTOR_R_IN1,
        PIN_MOTOR_R_IN2,
    };

    for (int8_t pin : motorPins) {
        if (pin >= 0) {
            pinMode(pin, OUTPUT);
            digitalWrite(pin, LOW);
        }
    }
}

void stopMotor(const char* reason) {
    if (motorActive) {
        Serial.printf("[MotorWiFi] stop: %s\n", reason);
    }
    motor.stop();
    motorActive = false;
    lastCommand = 'x';
}

void driveCommand(char command) {
    lastCommand = command;

    switch (command) {
        case 'w':
            motor.forward(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case 's':
            motor.backward(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case 'a':
            motor.turnLeft(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case 'd':
            motor.turnRight(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case '+':
            motorSpeed = min(motorSpeed + MOTOR_SPEED_STEP, MOTOR_SPEED_MAX);
            break;
        case '-':
            motorSpeed = max(motorSpeed - MOTOR_SPEED_STEP, MOTOR_SPEED_MIN);
            break;
        default:
            stopMotor("command stop");
            break;
    }
}

void sendStatus() {
    String response = "{";
    response += "\"command\":\"";
    response += lastCommand;
    response += "\",\"speed\":";
    response += motorSpeed;
    response += ",\"active\":";
    response += motorActive ? "true" : "false";
    response += "}";
    server.send(200, "application/json", response);
}

void handleCommand() {
    if (!server.hasArg("c") || server.arg("c").length() == 0) {
        server.send(400, "application/json", "{\"error\":\"missing command\"}");
        return;
    }

    const char command = static_cast<char>(tolower(server.arg("c")[0]));
    if (command == '=' || command == '+') {
        driveCommand('+');
    } else {
        driveCommand(command);
    }
    sendStatus();
}

void handleNotFound() {
    stopMotor("http 404");
    server.send(404, "text/plain", "Not found");
}

}  // namespace

void setup() {
    holdMotorPinsLowBeforeSerial();

    Serial.begin(115200);
    delay(1000);
    Serial.println("[MotorWiFi] Xiao-An WiFi motor manual bring-up");
    Serial.println("[MotorWiFi] Wheels must be lifted before testing.");

    motor.begin();
    motor.stop();

    WiFi.mode(WIFI_AP);
    const bool apStarted = WiFi.softAP(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("[MotorWiFi] AP %s: ssid=%s password=%s ip=%s\n",
                  apStarted ? "started" : "failed",
                  WIFI_SSID,
                  WIFI_PASSWORD,
                  WiFi.softAPIP().toString().c_str());

    server.on("/", HTTP_GET, []() {
        server.send_P(200, "text/html", INDEX_HTML);
    });
    server.on("/cmd", HTTP_GET, handleCommand);
    server.on("/status", HTTP_GET, sendStatus);
    server.onNotFound(handleNotFound);
    server.begin();
    Serial.println("[MotorWiFi] Open http://192.168.4.1 after joining XiaoAn-Motor.");
}

void loop() {
    server.handleClient();

    if (motorActive &&
        static_cast<int32_t>(millis() - motorHoldUntilMs) >= 0) {
        stopMotor("deadman timeout");
    }

    delay(5);
}
