#include <Arduino.h>
#include <TFT_eSPI.h>

#include "board_pins.h"

#ifndef PROBE_NAME
#define PROBE_NAME "unknown"
#endif

static TFT_eSPI tft;

static void rawInitAfterTftEspiBusInit() {
    Serial.println("[TFT_PROBE] applying raw ST7789 init sequence");
    tft.writecommand(0x01); // Software reset
    delay(150);
    tft.writecommand(0x11); // Sleep out
    delay(150);
    tft.writecommand(0x3A); // RGB565
    tft.writedata(0x55);
    tft.writecommand(0x36); // Landscape: MX | MV, RGB order
    tft.writedata(0x60);
    tft.writecommand(0x20); // Inversion off, matching the raw working backend
    tft.writecommand(0x13); // Normal display mode
    delay(20);
    tft.writecommand(0x29); // Display on
    delay(120);
}

static void fillAndLabel(uint16_t color, const char *label, uint16_t textColor) {
    tft.fillScreen(color);
    tft.setTextColor(textColor, color);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(label, tft.width() / 2, tft.height() / 2 - 14, 4);
    tft.drawString(PROBE_NAME, tft.width() / 2, tft.height() / 2 + 20, 2);

    tft.fillRect(0, 0, 20, 20, TFT_RED);
    tft.fillRect(tft.width() - 20, 0, 20, 20, TFT_GREEN);
    tft.fillRect(0, tft.height() - 20, 20, 20, TFT_BLUE);
    tft.fillRect(tft.width() - 20, tft.height() - 20, 20, 20, TFT_WHITE);
}

static void drawRotationPage(uint8_t rotation) {
    tft.setRotation(rotation);
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_CYAN, TFT_BLACK);
    tft.drawString("TFT_eSPI probe", 8, 8, 2);
    tft.drawString(PROBE_NAME, 8, 32, 2);
    tft.drawString(String("rotation=") + rotation, 8, 56, 2);
    tft.drawString(String("w=") + tft.width() + " h=" + tft.height(), 8, 80, 2);

    tft.drawRect(0, 0, tft.width(), tft.height(), TFT_WHITE);
    tft.fillRect(4, 4, 22, 22, TFT_RED);
    tft.fillRect(tft.width() - 26, 4, 22, 22, TFT_GREEN);
    tft.fillRect(4, tft.height() - 26, 22, 22, TFT_BLUE);
    tft.fillRect(tft.width() - 26, tft.height() - 26, 22, 22, TFT_YELLOW);

    for (int16_t x = 0; x < tft.width(); x += 20) {
        tft.drawFastVLine(x, 0, tft.height(), TFT_DARKGREY);
    }
    for (int16_t y = 0; y < tft.height(); y += 20) {
        tft.drawFastHLine(0, y, tft.width(), TFT_DARKGREY);
    }
}

void setup() {
    Serial.begin(115200);
    delay(400);
    Serial.println();
    Serial.println("[TFT_PROBE] boot");
    Serial.printf("[TFT_PROBE] name=%s\n", PROBE_NAME);

    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);

    tft.init();
#ifdef PROBE_RAW_INIT_AFTER_TFT
    rawInitAfterTftEspiBusInit();
#else
    tft.writecommand(0x11); // Sleep out, harmless if init already sent it.
    delay(120);
    tft.writecommand(0x29); // Display on, useful for odd ST7789 modules.
    delay(120);
#endif
}

void loop() {
    for (uint8_t r = 0; r < 4; ++r) {
        drawRotationPage(r);
        Serial.printf("[TFT_PROBE] rotation=%u w=%d h=%d\n", r, tft.width(), tft.height());
        delay(1800);
    }

    tft.setRotation(1);
    fillAndLabel(TFT_RED, "RED", TFT_WHITE);
    delay(900);
    fillAndLabel(TFT_GREEN, "GREEN", TFT_BLACK);
    delay(900);
    fillAndLabel(TFT_BLUE, "BLUE", TFT_WHITE);
    delay(900);
    fillAndLabel(TFT_WHITE, "WHITE", TFT_BLACK);
    delay(900);
    fillAndLabel(TFT_BLACK, "BLACK", TFT_CYAN);
    delay(900);
}
