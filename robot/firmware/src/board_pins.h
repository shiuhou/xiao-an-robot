#pragma once
/**
 * @file board_pins.h
 * @brief GOOUUU ESP32-S3-CAM wiring constants for Xiao An integrated harness.
 *
 * Canonical reference: hardware/wiring/esp32_pinout.md
 *
 * Integrated TFT map (GPIO14/21/42/43/44/48) coexists with OV2640 DVP.
 * Legacy bench TFT map (GPIO9/10/11/12) is available only through PlatformIO
 * `tft_legacy_pins` on explicit `*_legacy` envs.
 */

#include <stdint.h>

// ── OV2640 camera (GOOUUU FPC — fixed) ─────────────────────────────────────

constexpr int8_t CAM_PIN_PWDN = -1;
constexpr int8_t CAM_PIN_RESET = -1;
constexpr int8_t CAM_PIN_XCLK = 15;
constexpr int8_t CAM_PIN_SIOD = 4;
constexpr int8_t CAM_PIN_SIOC = 5;
constexpr int8_t CAM_PIN_D0 = 11;
constexpr int8_t CAM_PIN_D1 = 9;
constexpr int8_t CAM_PIN_D2 = 8;
constexpr int8_t CAM_PIN_D3 = 10;
constexpr int8_t CAM_PIN_D4 = 12;
constexpr int8_t CAM_PIN_D5 = 18;
constexpr int8_t CAM_PIN_D6 = 17;
constexpr int8_t CAM_PIN_D7 = 16;
constexpr int8_t CAM_PIN_VSYNC = 6;
constexpr int8_t CAM_PIN_HREF = 7;
constexpr int8_t CAM_PIN_PCLK = 13;

// ── TFT ST7789 2.4" — integrated map (default) ───────────────────────────────

#ifndef TFT_SCLK
#define TFT_SCLK 14
#endif
#ifndef TFT_MOSI
#define TFT_MOSI 21
#endif
#ifndef TFT_MISO
#define TFT_MISO -1
#endif
#ifndef TFT_CS
#define TFT_CS 42
#endif
#ifndef TFT_DC
#define TFT_DC 43
#endif
#ifndef TFT_RST
#define TFT_RST 44
#endif
#ifndef TFT_BL
#define TFT_BL 48
#endif
#ifndef TFT_BACKLIGHT_ON
#define TFT_BACKLIGHT_ON HIGH
#endif

// ── INMP441 microphone ───────────────────────────────────────────────────────

#ifndef VOICE_I2S_BCLK
#define VOICE_I2S_BCLK 39
#endif
#ifndef VOICE_I2S_WS
#define VOICE_I2S_WS 40
#endif
#ifndef VOICE_I2S_DIN
#define VOICE_I2S_DIN 41
#endif

// ── MAX98357A speaker amplifier ──────────────────────────────────────────────

#ifndef SPEAKER_I2S_BCLK
#define SPEAKER_I2S_BCLK 35
#endif
#ifndef SPEAKER_I2S_LRC
#define SPEAKER_I2S_LRC 36
#endif
#ifndef SPEAKER_I2S_DIN
#define SPEAKER_I2S_DIN 37
#endif
