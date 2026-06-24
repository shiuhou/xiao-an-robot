#include <Arduino.h>
#include <SPI.h>

#include "board_pins.h"
#include "motor_ctrl.h"

static constexpr int16_t TFT_W = 320;
static constexpr int16_t TFT_H = 240;
static constexpr uint32_t SPI_HZ = 10000000;

static void selectDisplay() {
    digitalWrite(TFT_CS, LOW);
}

static void unselectDisplay() {
    digitalWrite(TFT_CS, HIGH);
}

static void forceMotorStopPinsLow() {
    pinMode(PIN_MOTOR_L_IN1, OUTPUT);
    pinMode(PIN_MOTOR_L_IN2, OUTPUT);
    pinMode(PIN_MOTOR_R_IN1, OUTPUT);
    pinMode(PIN_MOTOR_R_IN2, OUTPUT);
    digitalWrite(PIN_MOTOR_L_IN1, LOW);
    digitalWrite(PIN_MOTOR_L_IN2, LOW);
    digitalWrite(PIN_MOTOR_R_IN1, LOW);
    digitalWrite(PIN_MOTOR_R_IN2, LOW);
}

static void setBacklightOn() {
    if (TFT_BL >= 0) {
        pinMode(TFT_BL, OUTPUT);
        digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);
    }
}

static void writeCommand(uint8_t command) {
    SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
    digitalWrite(TFT_DC, LOW);
    selectDisplay();
    SPI.transfer(command);
    unselectDisplay();
    digitalWrite(TFT_DC, HIGH);
    SPI.endTransaction();
}

static void writeData8(uint8_t data) {
    SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    SPI.transfer(data);
    unselectDisplay();
    SPI.endTransaction();
}

static void writeData16(uint16_t data) {
    SPI.transfer(static_cast<uint8_t>(data >> 8));
    SPI.transfer(static_cast<uint8_t>(data & 0xFF));
}

static void setAddressWindow(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    writeCommand(0x2A);
    writeData8(x0 >> 8);
    writeData8(x0 & 0xFF);
    writeData8(x1 >> 8);
    writeData8(x1 & 0xFF);

    writeCommand(0x2B);
    writeData8(y0 >> 8);
    writeData8(y0 & 0xFF);
    writeData8(y1 >> 8);
    writeData8(y1 & 0xFF);

    writeCommand(0x2C);
}

static void fillScreen(uint16_t color) {
    setAddressWindow(0, 0, TFT_W - 1, TFT_H - 1);
    SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    for (uint32_t i = 0; i < static_cast<uint32_t>(TFT_W) * TFT_H; ++i) {
        writeData16(color);
    }
    unselectDisplay();
    SPI.endTransaction();
}

static void initSt7789Raw() {
    Serial.println("[WIRETEST] raw ST7789 init start");

    pinMode(TFT_CS, OUTPUT);
    pinMode(TFT_DC, OUTPUT);
    pinMode(TFT_RST, OUTPUT);
    digitalWrite(TFT_CS, HIGH);
    digitalWrite(TFT_DC, HIGH);
    setBacklightOn();

    SPI.begin(TFT_SCLK, TFT_MISO, TFT_MOSI, TFT_CS);

    digitalWrite(TFT_RST, HIGH);
    delay(20);
    digitalWrite(TFT_RST, LOW);
    delay(30);
    digitalWrite(TFT_RST, HIGH);
    delay(150);

    writeCommand(0x01);
    delay(150);
    writeCommand(0x11);
    delay(150);
    writeCommand(0x3A);
    writeData8(0x55);
    writeCommand(0x36);
    writeData8(0x60);
    writeCommand(0x20);
    writeCommand(0x13);
    delay(20);
    writeCommand(0x29);
    delay(120);

    Serial.println("[WIRETEST] raw ST7789 init done");
}

struct ColorStep {
    const char *name;
    uint16_t color;
};

static const ColorStep STEPS[] = {
    {"RED", 0xF800},
    {"GREEN", 0x07E0},
    {"BLUE", 0x001F},
    {"WHITE", 0xFFFF},
    {"BLACK", 0x0000},
    {"CYAN", 0x07FF},
    {"YELLOW", 0xFFE0},
    {"MAGENTA", 0xF81F},
};

void setup() {
    Serial.begin(115200);
    delay(800);
    Serial.println();
    Serial.println("[WIRETEST] 2.4 inch ST7789 raw wiring test");
    forceMotorStopPinsLow();
    Serial.printf("[WIRETEST] motor pins forced LOW: L=%d/%d R=%d/%d\n",
                  PIN_MOTOR_L_IN1, PIN_MOTOR_L_IN2, PIN_MOTOR_R_IN1, PIN_MOTOR_R_IN2);
    Serial.printf("[WIRETEST] SCLK=%d MOSI=%d CS=%d DC=%d RST=%d BL=%d\n",
                  TFT_SCLK, TFT_MOSI, TFT_CS, TFT_DC, TFT_RST, TFT_BL);
    initSt7789Raw();
}

void loop() {
    forceMotorStopPinsLow();
    static uint8_t index = 0;
    const ColorStep &step = STEPS[index];
    Serial.printf("[WIRETEST] fill %s 0x%04X\n", step.name, step.color);
    fillScreen(step.color);

    setBacklightOn();
    delay(900);
    index = (index + 1) % (sizeof(STEPS) / sizeof(STEPS[0]));
}
