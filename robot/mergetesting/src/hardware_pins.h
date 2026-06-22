#pragma once
// hardware_pins.h — 引脚表（对齐 hardware/wiring/esp32_pinout.md 与 firmware bring-up）

// DRV8833 电机
#ifndef PIN_MOTOR_L_IN1
#define PIN_MOTOR_L_IN1 1
#endif
#ifndef PIN_MOTOR_L_IN2
#define PIN_MOTOR_L_IN2 2
#endif
#ifndef PIN_MOTOR_R_IN1
#define PIN_MOTOR_R_IN1 47
#endif
#ifndef PIN_MOTOR_R_IN2
#define PIN_MOTOR_R_IN2 38
#endif

// 128x160 ST7735 / 2.4" ST7789（引脚相同，不可与 OV2640 同接）
#ifndef TFT_MOSI
#define TFT_MOSI 11
#endif
#ifndef TFT_SCLK
#define TFT_SCLK 12
#endif
#ifndef TFT_CS
#define TFT_CS 10
#endif
#ifndef TFT_DC
#define TFT_DC 9
#endif
#ifndef TFT_RST
#define TFT_RST 14
#endif
#ifndef TFT_BL
#define TFT_BL 21
#endif

// INMP441 麦克风（voice_recognition_test）
#ifndef MIC_I2S_BCLK
#define MIC_I2S_BCLK 39
#endif
#ifndef MIC_I2S_WS
#define MIC_I2S_WS 40
#endif
#ifndef MIC_I2S_DIN
#define MIC_I2S_DIN 41
#endif

// MAX98357A 喇叭（speaker_amp_test）
#ifndef SPEAKER_I2S_BCLK
#define SPEAKER_I2S_BCLK 35
#endif
#ifndef SPEAKER_I2S_LRC
#define SPEAKER_I2S_LRC 36
#endif
#ifndef SPEAKER_I2S_DIN
#define SPEAKER_I2S_DIN 37
#endif
