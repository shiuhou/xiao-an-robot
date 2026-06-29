#include <Arduino.h>

#if MERGETEST_AUDIO_SHARED_I2S_DIAG

#include <driver/i2s.h>
#include <esp_err.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "embedded_tts_phrase.h"

#ifndef I2S_SHARED_BCLK
#define I2S_SHARED_BCLK 39
#endif
#ifndef I2S_SHARED_WS
#define I2S_SHARED_WS 40
#endif
#ifndef I2S_MIC_SD
#define I2S_MIC_SD 41
#endif
#ifndef I2S_SPK_DIN
#define I2S_SPK_DIN 47
#endif
#ifndef EMBEDDED_TTS_GAIN
#define EMBEDDED_TTS_GAIN 20
#endif
#ifndef AUDIO_DIAG_LOG_UART0
#define AUDIO_DIAG_LOG_UART0 1
#endif
#ifndef AUDIO_DIAG_UART0_RX
#define AUDIO_DIAG_UART0_RX 44
#endif
#ifndef AUDIO_DIAG_UART0_TX
#define AUDIO_DIAG_UART0_TX 43
#endif

#if AUDIO_DIAG_LOG_UART0
#define AUDIO_DIAG_LOG_SERIAL Serial0
#else
#define AUDIO_DIAG_LOG_SERIAL Serial
#endif

#if I2S_SHARED_BCLK == 35 || I2S_SHARED_BCLK == 36 || I2S_SHARED_BCLK == 37 || \
    I2S_SHARED_WS == 35 || I2S_SHARED_WS == 36 || I2S_SHARED_WS == 37 ||       \
    I2S_MIC_SD == 35 || I2S_MIC_SD == 36 || I2S_MIC_SD == 37 ||                \
    I2S_SPK_DIN == 35 || I2S_SPK_DIN == 36 || I2S_SPK_DIN == 37
#error "Audio shared I2S diagnostic must not use GPIO35/36/37"
#endif

namespace {

constexpr i2s_port_t MIC_RX_I2S_PORT = I2S_NUM_0;
constexpr i2s_port_t SPEAKER_TX_I2S_PORT = I2S_NUM_1;
constexpr uint32_t SAMPLE_RATE = EmbeddedTtsPhrase::SAMPLE_RATE;
constexpr uint32_t LISTEN_MS = 2000;
constexpr uint32_t SWITCH_TEST_CYCLES = 5;
constexpr uint32_t STABILITY_TEST_MS = 180000;
constexpr uint32_t POST_SPEAK_DELAY_MS = 1000;
constexpr size_t MIC_SAMPLE_COUNT = 512;
constexpr size_t PCM_FRAMES_PER_CHUNK = 128;
constexpr int16_t PCM_LEADING_TRIM_THRESHOLD = 16;
constexpr int16_t OUTPUT_PROBE_AMPLITUDE = 30000;
constexpr uint32_t OUTPUT_PROBE_FREQUENCY_HZ = 1000;
constexpr uint32_t OUTPUT_PROBE_DURATION_MS = 260;
constexpr int32_t VOICE_RMS_THRESHOLD = 300;
constexpr TickType_t I2S_IO_TIMEOUT = pdMS_TO_TICKS(50);

int32_t micSamples[MIC_SAMPLE_COUNT];
int16_t stereoBuffer[PCM_FRAMES_PER_CHUNK * 2];
bool i2sInstalled = false;
i2s_port_t installedI2SPort = MIC_RX_I2S_PORT;

struct MicStats {
  uint32_t frames = 0;
  uint32_t reads = 0;
  uint32_t lastBytes = 0;
  esp_err_t lastReadErr = ESP_OK;
  double rms = 0.0;
  int32_t peak = 0;
  bool voiceDetected = false;
};

const char* errName(esp_err_t err) {
  return esp_err_to_name(err);
}

void logHealth(const char* tag) {
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] %s free_heap=%u free_psram=%u stack_high_water_mark=%u\n",
      tag,
      static_cast<unsigned>(ESP.getFreeHeap()),
      static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)),
      static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)));
}

void forceSpeakerDinLow() {
  pinMode(I2S_SPK_DIN, OUTPUT);
  digitalWrite(I2S_SPK_DIN, LOW);
}

void uninstallI2S() {
  if (!i2sInstalled) {
    return;
  }
  i2s_stop(installedI2SPort);
  i2s_driver_uninstall(installedI2SPort);
  i2sInstalled = false;
}

esp_err_t installRxI2S() {
  forceSpeakerDinLow();
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX),
      .sample_rate = SAMPLE_RATE,
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
      .bck_io_num = I2S_SHARED_BCLK,
      .ws_io_num = I2S_SHARED_WS,
      .data_out_num = I2S_PIN_NO_CHANGE,
      .data_in_num = I2S_MIC_SD,
  };

  esp_err_t err = i2s_driver_install(MIC_RX_I2S_PORT, &config, 0, nullptr);
  if (err != ESP_OK) {
    AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] i2s_rx_install return code=%d name=%s\n", static_cast<int>(err), errName(err));
    return err;
  }
  i2sInstalled = true;
  installedI2SPort = MIC_RX_I2S_PORT;

  err = i2s_set_pin(MIC_RX_I2S_PORT, &pins);
  if (err != ESP_OK) {
    AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] i2s_rx_set_pin return code=%d name=%s\n", static_cast<int>(err), errName(err));
    uninstallI2S();
    return err;
  }
  i2s_zero_dma_buffer(MIC_RX_I2S_PORT);
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] i2s_rx_init ok");
  return ESP_OK;
}

void stopListen() {
  uninstallI2S();
  forceSpeakerDinLow();
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] i2s_rx_stop ok");
  logHealth("after_LISTEN");
}

int16_t convertMicSample(int32_t raw) {
  int32_t sample = raw >> 14;
  if (sample > INT16_MAX) {
    sample = INT16_MAX;
  } else if (sample < INT16_MIN) {
    sample = INT16_MIN;
  }
  return static_cast<int16_t>(sample);
}

MicStats listenFor(uint32_t durationMs) {
  MicStats stats;
  int64_t sumSquares = 0;
  const uint32_t started = millis();
  while (millis() - started < durationMs) {
    size_t bytesRead = 0;
    const esp_err_t err = i2s_read(
        MIC_RX_I2S_PORT,
        micSamples,
        sizeof(micSamples),
        &bytesRead,
        I2S_IO_TIMEOUT);
    stats.lastReadErr = err;
    stats.lastBytes = static_cast<uint32_t>(bytesRead);
    ++stats.reads;
    if (err != ESP_OK || bytesRead == 0) {
      vTaskDelay(1);
      continue;
    }

    const size_t count = bytesRead / sizeof(micSamples[0]);
    for (size_t i = 0; i < count; ++i) {
      const int16_t sample = convertMicSample(micSamples[i]);
      const int32_t absSample = abs(static_cast<int32_t>(sample));
      if (absSample > stats.peak) {
        stats.peak = absSample;
      }
      sumSquares += static_cast<int64_t>(sample) * sample;
      ++stats.frames;
    }
    vTaskDelay(1);
  }

  if (stats.frames > 0) {
    stats.rms = sqrt(static_cast<double>(sumSquares) / static_cast<double>(stats.frames));
  }
  stats.voiceDetected = stats.rms >= VOICE_RMS_THRESHOLD;
  return stats;
}

bool runListen(uint32_t durationMs) {
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] mode=LISTEN start");
  logHealth("before_LISTEN");
  const esp_err_t initErr = installRxI2S();
  if (initErr != ESP_OK) {
    stopListen();
    return false;
  }

  const MicStats stats = listenFor(durationMs);
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] i2s_read return code=%d name=%s reads=%u last_bytes=%u\n",
      static_cast<int>(stats.lastReadErr),
      errName(stats.lastReadErr),
      static_cast<unsigned>(stats.reads),
      static_cast<unsigned>(stats.lastBytes));
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] rms=%.1f peak=%ld voice_detected=%s frames=%u\n",
      stats.rms,
      static_cast<long>(stats.peak),
      stats.voiceDetected ? "true" : "false",
      static_cast<unsigned>(stats.frames));
  stopListen();
  return stats.frames > 0 && stats.lastReadErr == ESP_OK;
}

esp_err_t installTxI2S() {
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX),
      .sample_rate = SAMPLE_RATE,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
      .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 6,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = true,
  };
  const i2s_pin_config_t pins = {
      .bck_io_num = I2S_SHARED_BCLK,
      .ws_io_num = I2S_SHARED_WS,
      .data_out_num = I2S_SPK_DIN,
      .data_in_num = I2S_PIN_NO_CHANGE,
  };

  esp_err_t err = i2s_driver_install(SPEAKER_TX_I2S_PORT, &config, 0, nullptr);
  if (err != ESP_OK) {
    AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] i2s_tx_install return code=%d name=%s\n", static_cast<int>(err), errName(err));
    return err;
  }
  i2sInstalled = true;
  installedI2SPort = SPEAKER_TX_I2S_PORT;

  err = i2s_set_pin(SPEAKER_TX_I2S_PORT, &pins);
  if (err != ESP_OK) {
    AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] i2s_tx_set_pin return code=%d name=%s\n", static_cast<int>(err), errName(err));
    uninstallI2S();
    return err;
  }
  i2s_zero_dma_buffer(SPEAKER_TX_I2S_PORT);
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] i2s_tx_init ok");
  return ESP_OK;
}

void stopSpeak() {
  if (i2sInstalled) {
    i2s_zero_dma_buffer(installedI2SPort);
  }
  uninstallI2S();
  forceSpeakerDinLow();
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] i2s_tx_stop ok");
  logHealth("after_SPEAK");
}

int16_t readPcmS16Le(const uint8_t* pcm, size_t frameIndex) {
  const size_t byteIndex = frameIndex * sizeof(int16_t);
  return static_cast<int16_t>(
      static_cast<uint16_t>(pcm[byteIndex]) |
      (static_cast<uint16_t>(pcm[byteIndex + 1]) << 8));
}

int16_t scalePcmSample(int16_t sample) {
  const int32_t scaled = static_cast<int32_t>(sample) * EMBEDDED_TTS_GAIN;
  if (scaled > INT16_MAX) {
    return INT16_MAX;
  }
  if (scaled < INT16_MIN) {
    return INT16_MIN;
  }
  return static_cast<int16_t>(scaled);
}

size_t countLeadingQuietPcmFrames(const uint8_t* pcm, size_t frames) {
  size_t offset = 0;
  while (offset < frames && abs(static_cast<int32_t>(readPcmS16Le(pcm, offset))) <= PCM_LEADING_TRIM_THRESHOLD) {
    ++offset;
  }
  return offset;
}

bool writeStereoFrames(uint32_t frames, uint32_t* bytesWrittenOut) {
  const size_t bytesToWrite = frames * 2U * sizeof(int16_t);
  size_t bytesWritten = 0;
  const esp_err_t err = i2s_write(
      SPEAKER_TX_I2S_PORT,
      stereoBuffer,
      bytesToWrite,
      &bytesWritten,
      I2S_IO_TIMEOUT);
  if (bytesWrittenOut) {
    *bytesWrittenOut += static_cast<uint32_t>(bytesWritten);
  }
  if (err != ESP_OK || bytesWritten != bytesToWrite) {
    AUDIO_DIAG_LOG_SERIAL.printf(
        "[AudioDiag] i2s_write return code=%d name=%s bytes=%u/%u\n",
        static_cast<int>(err),
        errName(err),
        static_cast<unsigned>(bytesWritten),
        static_cast<unsigned>(bytesToWrite));
    return false;
  }
  return true;
}

bool playOutputProbeTone() {
  uint32_t bytesWrittenTotal = 0;
  uint32_t framesWritten = 0;
  uint32_t phase = 0;
  const uint32_t totalFrames = static_cast<uint32_t>(
      static_cast<uint64_t>(SAMPLE_RATE) * OUTPUT_PROBE_DURATION_MS / 1000);
  const uint32_t phaseStep = static_cast<uint32_t>(
      (static_cast<uint64_t>(OUTPUT_PROBE_FREQUENCY_HZ) << 32) / SAMPLE_RATE);
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] output_probe_tone frequency_hz=%u amplitude=%d duration_ms=%u\n",
      static_cast<unsigned>(OUTPUT_PROBE_FREQUENCY_HZ),
      OUTPUT_PROBE_AMPLITUDE,
      static_cast<unsigned>(OUTPUT_PROBE_DURATION_MS));

  while (framesWritten < totalFrames) {
    const uint32_t chunk = min<uint32_t>(PCM_FRAMES_PER_CHUNK, totalFrames - framesWritten);
    for (uint32_t i = 0; i < chunk; ++i) {
      phase += phaseStep;
      const int16_t sample = (phase & 0x80000000UL) ? OUTPUT_PROBE_AMPLITUDE : -OUTPUT_PROBE_AMPLITUDE;
      stereoBuffer[i * 2] = sample;
      stereoBuffer[i * 2 + 1] = sample;
    }
    if (!writeStereoFrames(chunk, &bytesWrittenTotal)) {
      AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] output_probe_tone failed bytes_written=%u\n", static_cast<unsigned>(bytesWrittenTotal));
      return false;
    }
    framesWritten += chunk;
    vTaskDelay(1);
  }

  memset(stereoBuffer, 0, sizeof(stereoBuffer));
  for (uint32_t i = 0; i < 4; ++i) {
    if (!writeStereoFrames(PCM_FRAMES_PER_CHUNK, &bytesWrittenTotal)) {
      AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] output_probe_tone silence failed bytes_written=%u\n", static_cast<unsigned>(bytesWrittenTotal));
      return false;
    }
    vTaskDelay(1);
  }
  AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] output_probe_tone done bytes_written=%u\n", static_cast<unsigned>(bytesWrittenTotal));
  return true;
}

bool playEmbeddedPhrase(uint32_t* bytesWrittenOut) {
  uint32_t bytesWrittenTotal = 0;
  const size_t frames = EmbeddedTtsPhrase::PCM_LEN / sizeof(int16_t);
  size_t offset = countLeadingQuietPcmFrames(EmbeddedTtsPhrase::PCM, frames);
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] pcm_samples=%u gain=%d text=%s skipped_leading=%u\n",
      static_cast<unsigned>(frames),
      EMBEDDED_TTS_GAIN,
      EmbeddedTtsPhrase::TEXT,
      static_cast<unsigned>(offset));

  while (offset < frames) {
    const uint32_t chunk = min<uint32_t>(PCM_FRAMES_PER_CHUNK, frames - offset);
    for (uint32_t i = 0; i < chunk; ++i) {
      const int16_t sample = scalePcmSample(readPcmS16Le(EmbeddedTtsPhrase::PCM, offset + i));
      stereoBuffer[i * 2] = sample;
      stereoBuffer[i * 2 + 1] = sample;
    }

    const size_t bytesToWrite = chunk * 2U * sizeof(int16_t);
    size_t bytesWritten = 0;
    const esp_err_t err = i2s_write(
        SPEAKER_TX_I2S_PORT,
        stereoBuffer,
        bytesToWrite,
        &bytesWritten,
        I2S_IO_TIMEOUT);
    const uint32_t writeIndex = bytesWrittenTotal / bytesToWrite + 1;
    if (writeIndex == 1 || (writeIndex % 64) == 0 || offset + chunk >= frames || err != ESP_OK) {
      AUDIO_DIAG_LOG_SERIAL.printf(
          "[AudioDiag] i2s_write return code=%d name=%s bytes=%u/%u write_index=%u\n",
          static_cast<int>(err),
          errName(err),
          static_cast<unsigned>(bytesWritten),
          static_cast<unsigned>(bytesToWrite),
          static_cast<unsigned>(writeIndex));
    }
    if (err != ESP_OK || bytesWritten != bytesToWrite) {
      if (bytesWrittenOut) {
        *bytesWrittenOut = bytesWrittenTotal;
      }
      return false;
    }
    bytesWrittenTotal += static_cast<uint32_t>(bytesWritten);
    offset += chunk;
    vTaskDelay(1);
  }

  i2s_zero_dma_buffer(SPEAKER_TX_I2S_PORT);
  vTaskDelay(pdMS_TO_TICKS(20));
  if (bytesWrittenOut) {
    *bytesWrittenOut = bytesWrittenTotal;
  }
  AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] bytes_written=%u\n", static_cast<unsigned>(bytesWrittenTotal));
  return true;
}

bool runSpeak() {
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] mode=SPEAK start");
  logHealth("before_SPEAK");
  const esp_err_t initErr = installTxI2S();
  if (initErr != ESP_OK) {
    stopSpeak();
    return false;
  }

  uint32_t bytesWritten = 0;
  const bool probeOk = playOutputProbeTone();
  const bool ok = probeOk && playEmbeddedPhrase(&bytesWritten);
  if (ok) {
    AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] playback_done ok");
  } else {
    AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] playback_done failed bytes_written=%u\n", static_cast<unsigned>(bytesWritten));
  }
  stopSpeak();
  return ok;
}

bool runListenSpeakCycle(uint32_t cycle) {
  AUDIO_DIAG_LOG_SERIAL.printf("[AudioDiag] cycle=%u start\n", static_cast<unsigned>(cycle));
  const bool listenOk = runListen(LISTEN_MS);
  vTaskDelay(pdMS_TO_TICKS(100));
  const bool speakOk = runSpeak();
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] cycle=%u done listen_ok=%s speak_ok=%s\n",
      static_cast<unsigned>(cycle),
      listenOk ? "true" : "false",
      speakOk ? "true" : "false");
  return listenOk && speakOk;
}

void runDiagnostics() {
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] boot shared I2S half-duplex diagnostic");
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] pins BCLK=%d WS=%d MIC_SD=%d SPK_DIN=%d\n",
      I2S_SHARED_BCLK,
      I2S_SHARED_WS,
      I2S_MIC_SD,
      I2S_SPK_DIN);
  AUDIO_DIAG_LOG_SERIAL.printf(
      "[AudioDiag] i2s_ports mic_rx=%d speaker_tx=%d\n",
      static_cast<int>(MIC_RX_I2S_PORT),
      static_cast<int>(SPEAKER_TX_I2S_PORT));
  logHealth("boot");

  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] test=1 speaker DIN GPIO47 phrase");
  runSpeak();
  vTaskDelay(pdMS_TO_TICKS(500));

  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] test=2 mic RMS");
  runListen(LISTEN_MS);
  vTaskDelay(pdMS_TO_TICKS(500));

  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] test=3 half-duplex switch x5");
  for (uint32_t i = 1; i <= SWITCH_TEST_CYCLES; ++i) {
    runListenSpeakCycle(i);
    vTaskDelay(pdMS_TO_TICKS(POST_SPEAK_DELAY_MS));
  }

  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] test=4 stability 180s");
  const uint32_t stabilityStart = millis();
  uint32_t cycle = 0;
  while (millis() - stabilityStart < STABILITY_TEST_MS) {
    ++cycle;
    runListenSpeakCycle(cycle);
    vTaskDelay(pdMS_TO_TICKS(POST_SPEAK_DELAY_MS));
    logHealth("stability");
  }
  AUDIO_DIAG_LOG_SERIAL.println("[AudioDiag] diag complete");
  logHealth("complete");
}

}  // namespace

void setup() {
  AUDIO_DIAG_LOG_SERIAL.begin(115200, SERIAL_8N1, AUDIO_DIAG_UART0_RX, AUDIO_DIAG_UART0_TX);
  delay(1500);
  forceSpeakerDinLow();
  runDiagnostics();
}

void loop() {
  logHealth("idle");
  delay(5000);
}

#endif  // MERGETEST_AUDIO_SHARED_I2S_DIAG
