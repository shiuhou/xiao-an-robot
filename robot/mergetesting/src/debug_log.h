#pragma once
// debug_log.h — 统一串口日志前缀

#include <Arduino.h>

#define LOGI(tag, fmt, ...) Serial.printf("[%s] " fmt "\n", tag, ##__VA_ARGS__)
#define LOGW(tag, fmt, ...) Serial.printf("[%s][WARN] " fmt "\n", tag, ##__VA_ARGS__)
#define LOGE(tag, fmt, ...) Serial.printf("[%s][ERR] " fmt "\n", tag, ##__VA_ARGS__)
