#include "mic_stream.h"
#include "board_pins.h"
#include "feature_flags.h"
#include "debug_log.h"

#if ENABLE_WS_INTEGRATED

#include "ws_client.h"
#include <driver/i2s.h>

namespace {

constexpr i2s_port_t MIC_I2S_PORT = I2S_NUM_0;
constexpr size_t SAMPLE_COUNT = 320;
constexpr uint32_t SEND_INTERVAL_MS = 100;
constexpr uint32_t MIC_SAMPLE_RATE = 16000;

int32_t samples[SAMPLE_COUNT];

bool installMicI2S() {
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = MIC_SAMPLE_RATE,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
      .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 6,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = false,
  };

  const i2s_pin_config_t pins = {
      .bck_io_num = VOICE_I2S_BCLK,
      .ws_io_num = VOICE_I2S_WS,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = VOICE_I2S_DIN,
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
  return raw >> 14;
}

}  // namespace

void MicStream::begin() {
  if (_active) {
    return;
  }
  _active = installMicI2S();
  if (_active) {
    LOGI("Mic", "INMP441 ready BCLK=%d WS=%d DIN=%d", VOICE_I2S_BCLK, VOICE_I2S_WS, VOICE_I2S_DIN);
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

bool MicStream::isActive() {
  return _active;
}

#else

void MicStream::begin() {
}

void MicStream::streamLoop() {
}

bool MicStream::isActive() {
  return _active;
}

#endif
