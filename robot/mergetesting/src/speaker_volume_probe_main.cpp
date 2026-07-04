#include <Arduino.h>

#if MERGETEST_SPEAKER_VOLUME_PROBE

#include <driver/i2s.h>
#include <cstring>

#ifndef MERGETEST_SPEAKER_BCLK
#define MERGETEST_SPEAKER_BCLK 39
#endif

#ifndef MERGETEST_SPEAKER_LRC
#define MERGETEST_SPEAKER_LRC 40
#endif

#ifndef MERGETEST_SPEAKER_DIN
#define MERGETEST_SPEAKER_DIN 41
#endif

#ifndef MERGETEST_SPEAKER_SAMPLE_RATE
#define MERGETEST_SPEAKER_SAMPLE_RATE 16000
#endif

namespace {

constexpr i2s_port_t SPEAKER_I2S_PORT = I2S_NUM_1;
constexpr size_t FRAMES_PER_BUFFER = 128;
constexpr uint32_t FIRST_PLAY_DELAY_MS = 1200;
constexpr uint32_t REPLAY_DELAY_MS = 7000;
constexpr uint32_t TONE_HZ = 700;
constexpr uint32_t TONE_MS = 650;
constexpr uint32_t GAP_MS = 350;

int16_t gStereoBuffer[FRAMES_PER_BUFFER * 2];
uint32_t gLastRunMs = 0;
bool gRanOnce = false;

bool installSpeakerI2S() {
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX),
      .sample_rate = MERGETEST_SPEAKER_SAMPLE_RATE,
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
      .bck_io_num = MERGETEST_SPEAKER_BCLK,
      .ws_io_num = MERGETEST_SPEAKER_LRC,
      .data_out_num = MERGETEST_SPEAKER_DIN,
      .data_in_num = I2S_PIN_NO_CHANGE,
  };

  if (i2s_driver_install(SPEAKER_I2S_PORT, &config, 0, nullptr) != ESP_OK) {
    return false;
  }
  if (i2s_set_pin(SPEAKER_I2S_PORT, &pins) != ESP_OK) {
    i2s_driver_uninstall(SPEAKER_I2S_PORT);
    return false;
  }
  i2s_zero_dma_buffer(SPEAKER_I2S_PORT);
  return true;
}

bool writeFrames(const int16_t* samples, uint32_t frames) {
  size_t bytesWritten = 0;
  const size_t bytesToWrite = frames * 2 * sizeof(int16_t);
  const esp_err_t err = i2s_write(
      SPEAKER_I2S_PORT,
      samples,
      bytesToWrite,
      &bytesWritten,
      pdMS_TO_TICKS(50));
  return err == ESP_OK && bytesWritten == bytesToWrite;
}

bool playSilence(uint32_t durationMs) {
  memset(gStereoBuffer, 0, sizeof(gStereoBuffer));
  const uint32_t totalFrames =
      static_cast<uint32_t>(static_cast<uint64_t>(MERGETEST_SPEAKER_SAMPLE_RATE) * durationMs / 1000);
  uint32_t framesWritten = 0;
  while (framesWritten < totalFrames) {
    const uint32_t chunk = min<uint32_t>(FRAMES_PER_BUFFER, totalFrames - framesWritten);
    if (!writeFrames(gStereoBuffer, chunk)) {
      return false;
    }
    framesWritten += chunk;
  }
  return true;
}

bool playSquareTone(uint32_t frequencyHz, uint32_t durationMs, int16_t amplitude) {
  const uint32_t totalFrames =
      static_cast<uint32_t>(static_cast<uint64_t>(MERGETEST_SPEAKER_SAMPLE_RATE) * durationMs / 1000);
  const uint32_t phaseStep =
      static_cast<uint32_t>((static_cast<uint64_t>(frequencyHz) << 32) / MERGETEST_SPEAKER_SAMPLE_RATE);
  uint32_t phase = 0;
  uint32_t framesWritten = 0;

  while (framesWritten < totalFrames) {
    const uint32_t chunk = min<uint32_t>(FRAMES_PER_BUFFER, totalFrames - framesWritten);
    for (uint32_t i = 0; i < chunk; ++i) {
      phase += phaseStep;
      const int16_t sample = (phase & 0x80000000UL) ? amplitude : static_cast<int16_t>(-amplitude);
      gStereoBuffer[i * 2] = sample;
      gStereoBuffer[i * 2 + 1] = sample;
    }
    if (!writeFrames(gStereoBuffer, chunk)) {
      return false;
    }
    framesWritten += chunk;
  }
  return true;
}

void runProbe() {
  Serial.println("[VolumeProbe] start amplitudes 2000 8000 16000 28000");
  if (!installSpeakerI2S()) {
    Serial.println("[VolumeProbe] i2s init failed");
    return;
  }

  const int16_t amplitudes[] = {2000, 8000, 16000, 28000};
  bool ok = true;
  for (int16_t amplitude : amplitudes) {
    Serial.printf("[VolumeProbe] tone amplitude=%d\n", amplitude);
    ok = playSquareTone(TONE_HZ, TONE_MS, amplitude) && ok;
    ok = playSilence(GAP_MS) && ok;
  }

  i2s_zero_dma_buffer(SPEAKER_I2S_PORT);
  i2s_driver_uninstall(SPEAKER_I2S_PORT);
  Serial.printf("[VolumeProbe] done ok=%s\n", ok ? "true" : "false");
  gLastRunMs = millis();
  gRanOnce = true;
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(FIRST_PLAY_DELAY_MS);
  Serial.println("[VolumeProbe] boot");
  runProbe();
}

void loop() {
  if (gRanOnce && millis() - gLastRunMs > REPLAY_DELAY_MS) {
    runProbe();
  }
  delay(20);
}

#endif  // MERGETEST_SPEAKER_VOLUME_PROBE
