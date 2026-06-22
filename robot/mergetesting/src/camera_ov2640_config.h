#pragma once

/**
 * OV2640 引脚与 sensor 调参（与 robot/firmware motor_cam_wifi_manual 一致）。
 * GOOUUU ESP32-S3 + OV2640 模块。
 */

#include "esp_camera.h"

#ifndef MERGETEST_CAMERA_FB_COUNT
#define MERGETEST_CAMERA_FB_COUNT 2
#endif

namespace ov2640 {

constexpr int PIN_PWDN = -1;
constexpr int PIN_RESET = -1;
constexpr int PIN_XCLK = 15;
constexpr int PIN_SIOD = 4;
constexpr int PIN_SIOC = 5;
constexpr int PIN_D0 = 11;
constexpr int PIN_D1 = 9;
constexpr int PIN_D2 = 8;
constexpr int PIN_D3 = 10;
constexpr int PIN_D4 = 12;
constexpr int PIN_D5 = 18;
constexpr int PIN_D6 = 17;
constexpr int PIN_D7 = 16;
constexpr int PIN_VSYNC = 6;
constexpr int PIN_HREF = 7;
constexpr int PIN_PCLK = 13;

/**
 * 填充 esp_camera 初始化结构（PSRAM、GRAB_LATEST、10MHz XCLK）。
 * @param config 输出配置
 * @param frameSize FRAMESIZE_QVGA 或 FRAMESIZE_VGA
 * @param quality JPEG 质量 0–63（越小画质越高）
 */
inline void fillCameraConfig(camera_config_t* config, framesize_t frameSize, int quality) {
  if (!config) {
    return;
  }

  *config = {};
  config->ledc_channel = LEDC_CHANNEL_7;
  config->ledc_timer = LEDC_TIMER_1;
  config->pin_d0 = PIN_D0;
  config->pin_d1 = PIN_D1;
  config->pin_d2 = PIN_D2;
  config->pin_d3 = PIN_D3;
  config->pin_d4 = PIN_D4;
  config->pin_d5 = PIN_D5;
  config->pin_d6 = PIN_D6;
  config->pin_d7 = PIN_D7;
  config->pin_xclk = PIN_XCLK;
  config->pin_pclk = PIN_PCLK;
  config->pin_vsync = PIN_VSYNC;
  config->pin_href = PIN_HREF;
  config->pin_sccb_sda = PIN_SIOD;
  config->pin_sccb_scl = PIN_SIOC;
  config->pin_pwdn = PIN_PWDN;
  config->pin_reset = PIN_RESET;
  config->xclk_freq_hz = 10000000;
  config->pixel_format = PIXFORMAT_JPEG;
  config->frame_size = frameSize;
  config->jpeg_quality = quality;
  config->fb_count = psramFound() ? MERGETEST_CAMERA_FB_COUNT : 1;
  config->fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config->grab_mode = CAMERA_GRAB_LATEST;
  config->sccb_i2c_port = 1;
}

/**
 * 自动曝光/增益与亮度（室内偏暗场景）。
 * @param sensor esp_camera sensor 句柄
 */
inline void tuneCameraSensor(sensor_t* sensor) {
  if (!sensor) {
    return;
  }

  sensor->set_brightness(sensor, 1);
  sensor->set_contrast(sensor, 0);
  sensor->set_saturation(sensor, 0);
  sensor->set_sharpness(sensor, 0);
  sensor->set_whitebal(sensor, 1);
  sensor->set_awb_gain(sensor, 1);
  sensor->set_exposure_ctrl(sensor, 1);
  sensor->set_gain_ctrl(sensor, 1);
  sensor->set_aec2(sensor, 1);
  sensor->set_ae_level(sensor, 1);
  sensor->set_gainceiling(sensor, GAINCEILING_8X);
  sensor->set_lenc(sensor, 1);
  sensor->set_dcw(sensor, 1);
}

}  // namespace ov2640
