#include "motor_ctrl.h"
#include "protocol.h"

// ── ISR flags (volatile, written only from interrupt context) ─────────────────
static volatile bool _frontLimitHit = false;
static volatile bool _backLimitHit  = false;

// Use high LEDC channels (timers 2/3) so esp_camera_init() on timer 1 does not
// clobber right-motor PWM when camera + motor are both enabled.
constexpr uint8_t MOTOR_CH_L_IN1 = 12;
constexpr uint8_t MOTOR_CH_L_IN2 = 13;
constexpr uint8_t MOTOR_CH_R_IN1 = 14;
constexpr uint8_t MOTOR_CH_R_IN2 = 15;

static const char* motorName(uint8_t motor) {
    return motor == 0 ? "left" : "right";
}

static uint8_t motorForwardChannel(uint8_t motor) {
    if (motor == 0) {
        return MOTOR_LEFT_FORWARD_USES_IN1 ? MOTOR_CH_L_IN1 : MOTOR_CH_L_IN2;
    }
    return MOTOR_RIGHT_FORWARD_USES_IN1 ? MOTOR_CH_R_IN1 : MOTOR_CH_R_IN2;
}

static uint8_t motorReverseChannel(uint8_t motor) {
    if (motor == 0) {
        return MOTOR_LEFT_FORWARD_USES_IN1 ? MOTOR_CH_L_IN2 : MOTOR_CH_L_IN1;
    }
    return MOTOR_RIGHT_FORWARD_USES_IN1 ? MOTOR_CH_R_IN2 : MOTOR_CH_R_IN1;
}

void IRAM_ATTR onFrontLimit() { _frontLimitHit = true; }
void IRAM_ATTR onBackLimit()  { _backLimitHit  = true; }

// ── begin() ──────────────────────────────────────────────────────────────────

void MotorController::begin() {
    Serial.println("[Motor] begin()");
    Serial.printf("[Motor] pins: L_IN1=%d L_IN2=%d R_IN1=%d R_IN2=%d\n",
                  PIN_MOTOR_L_IN1,
                  PIN_MOTOR_L_IN2,
                  PIN_MOTOR_R_IN1,
                  PIN_MOTOR_R_IN2);
    Serial.printf("[Motor] forward map: left uses %s, right uses %s\n",
                  MOTOR_LEFT_FORWARD_USES_IN1 ? "L_IN1/GPIO1" : "L_IN2/GPIO2",
                  MOTOR_RIGHT_FORWARD_USES_IN1 ? "R_IN1/GPIO3" : "R_IN2/GPIO48");

    // Motor output pins
    pinMode(PIN_MOTOR_L_IN1, OUTPUT);
    pinMode(PIN_MOTOR_L_IN2, OUTPUT);
    pinMode(PIN_MOTOR_R_IN1, OUTPUT);
    pinMode(PIN_MOTOR_R_IN2, OUTPUT);

    // Attach all four motor pins to individual LEDC channels so we can PWM
    // both IN1 and IN2 independently — needed for variable speed in reverse.
    // ledcAttach(pin, freq_hz, resolution_bits) — Arduino ESP32 3.x API
    const uint32_t freqL1 = ledcSetup(MOTOR_CH_L_IN1, MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RES_BITS);
    const uint32_t freqL2 = ledcSetup(MOTOR_CH_L_IN2, MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RES_BITS);
    const uint32_t freqR1 = ledcSetup(MOTOR_CH_R_IN1, MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RES_BITS);
    const uint32_t freqR2 = ledcSetup(MOTOR_CH_R_IN2, MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RES_BITS);
    if (freqL1 == 0 || freqL2 == 0 || freqR1 == 0 || freqR2 == 0) {
        Serial.println("[Motor] ERROR: LEDC setup failed — check channel/timer conflicts");
    }
    ledcAttachPin(PIN_MOTOR_L_IN1, MOTOR_CH_L_IN1);
    ledcAttachPin(PIN_MOTOR_L_IN2, MOTOR_CH_L_IN2);
    ledcAttachPin(PIN_MOTOR_R_IN1, MOTOR_CH_R_IN1);
    ledcAttachPin(PIN_MOTOR_R_IN2, MOTOR_CH_R_IN2);
    Serial.printf("[Motor] PWM channels attached ch=%u,%u,%u,%u freq=%lu Hz\n",
                  MOTOR_CH_L_IN1,
                  MOTOR_CH_L_IN2,
                  MOTOR_CH_R_IN1,
                  MOTOR_CH_R_IN2,
                  static_cast<unsigned long>(freqL1));

    if (PIN_LIMIT_FRONT >= 0) {
        pinMode(PIN_LIMIT_FRONT, INPUT_PULLUP);
        _frontLimitHit = (digitalRead(PIN_LIMIT_FRONT) == LOW);
        attachInterrupt(digitalPinToInterrupt(PIN_LIMIT_FRONT), onFrontLimit, FALLING);
        Serial.printf("[Motor] front limit enabled on GPIO%d\n", PIN_LIMIT_FRONT);
    } else {
        Serial.println("[Motor] front limit disabled");
    }

    if (PIN_LIMIT_BACK >= 0) {
        pinMode(PIN_LIMIT_BACK, INPUT_PULLUP);
        _backLimitHit = (digitalRead(PIN_LIMIT_BACK) == LOW);
        attachInterrupt(digitalPinToInterrupt(PIN_LIMIT_BACK), onBackLimit, FALLING);
        Serial.printf("[Motor] back limit enabled on GPIO%d\n", PIN_LIMIT_BACK);
    } else {
        Serial.println("[Motor] back limit disabled");
    }

    stop();
    Serial.println("[Motor] begin() — pins ready, LEDC attached, interrupts armed");
}

// ── setMotor() ───────────────────────────────────────────────────────────────
// DRV8833-style phase/enable test mode:
//   forward channel = PWM, reverse channel = 0 -> forward
//   forward channel = 0, reverse channel = PWM -> reverse
//   both channels = 0 -> coast/stop for safe bench bring-up

void MotorController::setMotor(uint8_t motor, int dir, int speed) {
    const uint8_t chForward = motorForwardChannel(motor);
    const uint8_t chReverse = motorReverseChannel(motor);
    const int duty = constrain(speed, 0, 255);
    int dutyForward = 0;
    int dutyReverse = 0;

    if (dir == 1) {
        dutyForward = duty;
    } else if (dir == -1) {
        dutyReverse = duty;
    }

    ledcWrite(chForward, dutyForward);
    ledcWrite(chReverse, dutyReverse);

    Serial.printf("[Motor] motor=%s dir=%d speed=%d -> forward_ch%d=%d reverse_ch%d=%d\n",
                  motorName(motor),
                  dir,
                  speed,
                  chForward,
                  dutyForward,
                  chReverse,
                  dutyReverse);
}

void MotorController::debugDriveRaw(int lIn1, int lIn2, int rIn1, int rIn2, uint32_t durationMs) {
    lIn1 = constrain(lIn1, 0, 255);
    lIn2 = constrain(lIn2, 0, 255);
    rIn1 = constrain(rIn1, 0, 255);
    rIn2 = constrain(rIn2, 0, 255);

    Serial.printf("[MotorRaw] GPIO1/L_IN1=%d GPIO2/L_IN2=%d GPIO3/R_IN1=%d GPIO48/R_IN2=%d for %lu ms\n",
                  lIn1,
                  lIn2,
                  rIn1,
                  rIn2,
                  static_cast<unsigned long>(durationMs));

    ledcWrite(MOTOR_CH_L_IN1, lIn1);
    ledcWrite(MOTOR_CH_L_IN2, lIn2);
    ledcWrite(MOTOR_CH_R_IN1, rIn1);
    ledcWrite(MOTOR_CH_R_IN2, rIn2);
    delay(durationMs);
    stop();
}

// ── stop() ───────────────────────────────────────────────────────────────────

void MotorController::stop() {
    setMotor(0, 0, 0);   // brake left
    setMotor(1, 0, 0);   // brake right
    Serial.println("[Motor] stop()");
}

// ── Raw indefinite drives (non-blocking) ─────────────────────────────────────

void MotorController::forward(int speed) {
    Serial.printf("[Motor] forward(speed=%d)\n", speed);
    setMotor(0,  1, speed);
    setMotor(1,  1, speed);
}

void MotorController::backward(int speed) {
    Serial.printf("[Motor] backward(speed=%d)\n", speed);
    setMotor(0, -1, speed);
    setMotor(1, -1, speed);
}

void MotorController::turnLeft(int speed) {
    Serial.printf("[Motor] turnLeft(speed=%d)\n", speed);
    setMotor(0, -1, speed);   // left wheel backward
    setMotor(1,  1, speed);   // right wheel forward
}

void MotorController::turnRight(int speed) {
    Serial.printf("[Motor] turnRight(speed=%d)\n", speed);
    setMotor(0,  1, speed);   // left wheel forward
    setMotor(1, -1, speed);   // right wheel backward
}

// ── moveForward() ────────────────────────────────────────────────────────────
// Drives forward until distance_cm is covered OR front limit switch fires.
// Distance is estimated by time: t = distance / (max_speed * duty_fraction).

void MotorController::moveForward(int speed, float distance_cm) {
    _frontLimitHit = false;   // clear stale flag before motion

    float   dutyFrac = constrain(speed, 1, 255) / 255.0f;
    float   secsEst  = distance_cm / (DRIVE_CM_PER_SEC * dutyFrac);
    uint32_t durMs   = (uint32_t)(secsEst * 1000.0f);

    Serial.printf("[Motor] moveForward start — speed=%d dist=%.1f cm est=%u ms\n",
                  speed, distance_cm, durMs);

    setMotor(0, 1, speed);
    setMotor(1, 1, speed);

    uint32_t t0 = millis();
    while (!_frontLimitHit && (millis() - t0 < durMs)) {
        yield();   // allow RTOS / watchdog to run between ticks
    }

    stop();

    if (_frontLimitHit) {
        Serial.println("[Motor] moveForward stopped — front limit triggered");
    } else {
        Serial.printf("[Motor] moveForward stopped — distance reached (%.1f cm)\n",
                      distance_cm);
    }
}

// ── moveBackward() ───────────────────────────────────────────────────────────
// Drives backward until the back limit switch fires (robot fully docked).
// Safety: also stops after DOCK_TIMEOUT_MS to prevent runaway.

void MotorController::moveBackward(int speed) {
    _backLimitHit = false;   // clear stale flag before motion

    constexpr uint32_t DOCK_TIMEOUT_MS = 10000;   // 10 s max reverse travel

    Serial.printf("[Motor] moveBackward start — speed=%d (timeout %u ms)\n",
                  speed, DOCK_TIMEOUT_MS);

    setMotor(0, -1, speed);
    setMotor(1, -1, speed);

    uint32_t t0 = millis();
    while (!_backLimitHit && (millis() - t0 < DOCK_TIMEOUT_MS)) {
        yield();
    }

    stop();

    if (_backLimitHit) {
        Serial.println("[Motor] moveBackward stopped — docked (back limit triggered)");
    } else {
        Serial.println("[Motor] moveBackward stopped — timeout (did not dock)");
    }
}

// ── turn() ───────────────────────────────────────────────────────────────────
// Pivot turn by angle_deg: positive = right, negative = left.
// Duration is estimated from TURN_MS_PER_DEG calibration constant.

void MotorController::turn(float angle_deg) {
    if (angle_deg == 0.0f) return;

    uint32_t durMs = (uint32_t)(fabsf(angle_deg) * TURN_MS_PER_DEG);
    const char* dir = (angle_deg > 0) ? "right" : "left";

    Serial.printf("[Motor] turn start — %.1f deg (%s) est=%u ms\n",
                  angle_deg, dir, durMs);

    if (angle_deg > 0) {
        setMotor(0,  1, TURN_DEFAULT_SPEED);   // left fwd
        setMotor(1, -1, TURN_DEFAULT_SPEED);   // right bwd
    } else {
        setMotor(0, -1, TURN_DEFAULT_SPEED);   // left bwd
        setMotor(1,  1, TURN_DEFAULT_SPEED);   // right fwd
    }

    uint32_t t0 = millis();
    while (millis() - t0 < durMs) {
        yield();
    }

    stop();
    Serial.printf("[Motor] turn stopped — %.1f deg %s complete\n", angle_deg, dir);
}

// ── isDocked() ───────────────────────────────────────────────────────────────
// Returns true if the back limit switch is currently pressed (active-LOW).

bool MotorController::isDocked() {
    if (PIN_LIMIT_BACK < 0) {
        return false;
    }

    return digitalRead(PIN_LIMIT_BACK) == LOW;
}

// ── execute() ────────────────────────────────────────────────────────────────
// Maps MotionAction protocol strings (from docs/protocol.md) to motion calls.
// param meaning depends on action:
//   turn             → angle_deg
//   move_out_of_dock → distance_cm (default 10 cm if 0)

void MotorController::execute(const char* action, float param) {
    Serial.printf("[Motor] execute(\"%s\", %.1f)\n", action, param);

    if (strcmp(action, MotionAction::MOVE_OUT_OF_DOCK) == 0) {
        float dist = (param > 0.0f) ? param : 10.0f;
        moveForward(200, dist);

    } else if (strcmp(action, MotionAction::MOVE_BACK_TO_DOCK) == 0) {
        moveBackward(180);

    } else if (strcmp(action, MotionAction::TURN) == 0) {
        turn(param);

    } else if (strcmp(action, MotionAction::STOP) == 0) {
        stop();

    } else {
        // NOD_HEAD, TILT_HEAD, WIGGLE_EARS are servo actions — not handled here
        Serial.printf("[Motor] execute: action \"%s\" not a motor action, skipping\n",
                      action);
    }
}
