#pragma once
// hardware_pins.h — 引脚表（对齐 hardware/wiring/esp32_pinout.md）

// DRV8833 电机
#ifndef PIN_MOTOR_L_IN1
#define PIN_MOTOR_L_IN1 1
#endif
#ifndef PIN_MOTOR_L_IN2
#define PIN_MOTOR_L_IN2 2
#endif
#ifndef PIN_MOTOR_R_IN1
#define PIN_MOTOR_R_IN1 3
#endif
#ifndef PIN_MOTOR_R_IN2
#define PIN_MOTOR_R_IN2 48
#endif

// 2.4" ST7789 整合线束（与 OV2640 可同接）
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
#define TFT_BL -1
#endif
#ifndef TFT_BACKLIGHT_ON
#define TFT_BACKLIGHT_ON HIGH
#endif

// INMP441 麦克风
#ifndef MIC_I2S_BCLK
#define MIC_I2S_BCLK 39
#endif
#ifndef MIC_I2S_WS
#define MIC_I2S_WS 40
#endif
#ifndef MIC_I2S_DIN
#define MIC_I2S_DIN 41
#endif

// MAX98357A 喇叭
#ifndef SPEAKER_I2S_BCLK
#define SPEAKER_I2S_BCLK 35
#endif
#ifndef SPEAKER_I2S_LRC
#define SPEAKER_I2S_LRC 36
#endif
#ifndef SPEAKER_I2S_DIN
#define SPEAKER_I2S_DIN 37
#endif
