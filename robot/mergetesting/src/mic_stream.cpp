#include "mic_stream.h"
#include "ws_client.h"
#include "config.h"
#include "hardware_pins.h"
#include "debug_log.h"

#if MERGETEST_ENABLE_MIC

#include <driver/i2s.h>
#include <math.h>

namespace {

#ifndef MERGETEST_MIC_CHANNEL_FORMAT
#define MERGETEST_MIC_CHANNEL_FORMAT I2S_CHANNEL_FMT_ONLY_LEFT
#endif

#ifndef MERGETEST_MIC_SHIFT_BITS
#define MERGETEST_MIC_SHIFT_BITS 14
#endif

#ifndef MERGETEST_MIC_SEND_INTERVAL_MS
#define MERGETEST_MIC_SEND_INTERVAL_MS 100
#endif

constexpr i2s_port_t MIC_I2S_PORT = I2S_NUM_0;
constexpr size_t SAMPLE_COUNT = 320;  // 20ms @ 16kHz mono
constexpr uint32_t SEND_INTERVAL_MS = MERGETEST_MIC_SEND_INTERVAL_MS;

int32_t samples[SAMPLE_COUNT];

bool installMicI2S() {
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = MERGETEST_SPEAKER_SAMPLE_RATE,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = MERGETEST_MIC_CHANNEL_FORMAT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 6,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = false,
  };

  const i2s_pin_config_t pins = {
      .bck_io_num = MIC_I2S_BCLK,
      .ws_io_num = MIC_I2S_WS,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = MIC_I2S_DIN,
  };

  if (i2s_driver_install(MIC_I2S_PORT, &config, 0, nullptr) != ESP_OK) {
    return false;
  }
  if (i2s_set_pin(MIC_I2S_PORT, &pins) != ESP_OK) {
    i2s_driver_uninstall(MIC_I2S_PORT);
    return false;
  }
  i2s_zero_dma_buffer(MIC_I2S_PORT);
  return true;
}

int32_t convertSample(int32_t raw) {
  return raw >> MERGETEST_MIC_SHIFT_BITS;
}

}  // namespace

void MicStream::begin() {
  if (_active) {
    return;
  }
  _active = installMicI2S();
  if (_active) {
    LOGI(
        "Mic",
        "INMP441 ready BCLK=%d WS=%d DIN=%d shift=%d send_interval_ms=%u",
        MIC_I2S_BCLK,
        MIC_I2S_WS,
        MIC_I2S_DIN,
        MERGETEST_MIC_SHIFT_BITS,
        static_cast<unsigned>(SEND_INTERVAL_MS));
  } else {
    LOGE("Mic", "INMP441 init failed");
  }
}

void MicStream::streamLoop(WSClient& ws) {
  if (!_active || !ws.isAudioConnected()) {
    return;
  }

  size_t bytesRead = 0;
  if (i2s_read(MIC_I2S_PORT, samples, sizeof(samples), &bytesRead, pdMS_TO_TICKS(10)) != ESP_OK ||
      bytesRead == 0) {
    return;
  }

  const uint32_t now = millis();
  if (now - _lastSendMs < SEND_INTERVAL_MS) {
    return;
  }
  _lastSendMs = now;

  const size_t count = bytesRead / sizeof(samples[0]);
  int16_t pcm[SAMPLE_COUNT];
  for (size_t i = 0; i < count && i < SAMPLE_COUNT; ++i) {
    pcm[i] = static_cast<int16_t>(convertSample(samples[i]));
  }

  ++_chunkId;
  ws.sendAudioChunkMeta(_chunkId);
  ws.sendAudioBinary(reinterpret_cast<const uint8_t*>(pcm), count * sizeof(int16_t));
}

bool MicStream::isActive() const {
  return _active;
}

#else

void MicStream::begin() {}
void MicStream::streamLoop(WSClient&) {}
bool MicStream::isActive() const { return false; }

#endif
