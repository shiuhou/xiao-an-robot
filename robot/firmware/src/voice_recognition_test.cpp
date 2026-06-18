#include <Arduino.h>
#include <driver/i2s.h>

#ifndef VOICE_I2S_BCLK
#define VOICE_I2S_BCLK 39
#endif

#ifndef VOICE_I2S_WS
#define VOICE_I2S_WS 40
#endif

#ifndef VOICE_I2S_DIN
#define VOICE_I2S_DIN 41
#endif

#ifndef VOICE_SAMPLE_RATE
#define VOICE_SAMPLE_RATE 16000
#endif

#ifndef VOICE_THRESHOLD_RMS
#define VOICE_THRESHOLD_RMS 650
#endif

#ifndef VOICE_LOUD_THRESHOLD_RMS
#define VOICE_LOUD_THRESHOLD_RMS 4000
#endif

static constexpr i2s_port_t MIC_I2S_PORT = I2S_NUM_0;
static constexpr size_t SAMPLE_COUNT = 512;
static constexpr uint32_t STATUS_INTERVAL_MS = 250;
static constexpr uint32_t CALIBRATION_MS = 3000;
static constexpr int32_t MAX_REASONABLE_SAMPLE = 2000000;

static int32_t samples[SAMPLE_COUNT];
static uint32_t bootMs = 0;
static uint32_t lastStatusMs = 0;
static uint32_t calibrationFrames = 0;
static uint64_t calibrationRmsSum = 0;
static uint32_t calibratedNoiseFloor = 0;

static int32_t convertSample(int32_t raw) {
    int32_t sample = raw >> 14;
    if (sample > MAX_REASONABLE_SAMPLE) {
        sample = MAX_REASONABLE_SAMPLE;
    } else if (sample < -MAX_REASONABLE_SAMPLE) {
        sample = -MAX_REASONABLE_SAMPLE;
    }
    return sample;
}

static bool installMicI2S() {
    const i2s_config_t config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = VOICE_SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 6,
        .dma_buf_len = 256,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0,
        .mclk_multiple = I2S_MCLK_MULTIPLE_DEFAULT,
        .bits_per_chan = I2S_BITS_PER_CHAN_32BIT,
    };

    const i2s_pin_config_t pins = {
        .mck_io_num = I2S_PIN_NO_CHANGE,
        .bck_io_num = VOICE_I2S_BCLK,
        .ws_io_num = VOICE_I2S_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = VOICE_I2S_DIN,
    };

    esp_err_t err = i2s_driver_install(MIC_I2S_PORT, &config, 0, nullptr);
    if (err != ESP_OK) {
        Serial.printf("[VoiceTest][ERR] i2s_driver_install failed: %d\n", err);
        return false;
    }

    err = i2s_set_pin(MIC_I2S_PORT, &pins);
    if (err != ESP_OK) {
        Serial.printf("[VoiceTest][ERR] i2s_set_pin failed: %d\n", err);
        i2s_driver_uninstall(MIC_I2S_PORT);
        return false;
    }

    i2s_zero_dma_buffer(MIC_I2S_PORT);
    return true;
}

static uint32_t dynamicVoiceThreshold() {
    const uint32_t noiseBased = calibratedNoiseFloor + max<uint32_t>(350, calibratedNoiseFloor / 2);
    return max<uint32_t>(VOICE_THRESHOLD_RMS, noiseBased);
}

static void printWiring() {
    Serial.println();
    Serial.println("[VoiceTest] INMP441 wiring:");
    Serial.printf("[VoiceTest] VDD -> 3V3, GND -> GND, SCK/BCLK -> GPIO%d\n", VOICE_I2S_BCLK);
    Serial.printf("[VoiceTest] WS/LRCL -> GPIO%d, SD/DOUT -> GPIO%d, L/R -> GND\n",
                  VOICE_I2S_WS,
                  VOICE_I2S_DIN);
    Serial.println("[VoiceTest] Keep L/R tied to GND for LEFT channel. Tie L/R to 3V3 only if you change the code to RIGHT channel.");
}

void setup() {
    Serial.begin(115200);
    delay(1500);

    Serial.println("[VoiceTest] Xiao-An INMP441 voice activity test");
    Serial.printf("[VoiceTest] sample_rate=%d threshold=%d loud_threshold=%d\n",
                  VOICE_SAMPLE_RATE,
                  VOICE_THRESHOLD_RMS,
                  VOICE_LOUD_THRESHOLD_RMS);
    printWiring();

    if (!installMicI2S()) {
        Serial.println("[VoiceTest][ERR] Mic init failed. Check pins and power, then reset.");
        while (true) {
            delay(1000);
        }
    }

    bootMs = millis();
    Serial.printf("[VoiceTest] Calibrating noise floor for %lu ms. Keep quiet.\n",
                  (unsigned long)CALIBRATION_MS);
}

void loop() {
    size_t bytesRead = 0;
    const esp_err_t err = i2s_read(
        MIC_I2S_PORT,
        samples,
        sizeof(samples),
        &bytesRead,
        pdMS_TO_TICKS(100));

    if (err != ESP_OK || bytesRead == 0) {
        Serial.printf("[VoiceTest][ERR] i2s_read failed: err=%d bytes=%u\n",
                      err,
                      (unsigned)bytesRead);
        delay(200);
        return;
    }

    const size_t count = bytesRead / sizeof(samples[0]);
    int32_t peak = 0;
    int64_t sumSquares = 0;
    int64_t dcSum = 0;

    for (size_t i = 0; i < count; ++i) {
        const int32_t sample = convertSample(samples[i]);
        const int32_t absSample = abs(sample);
        peak = max(peak, absSample);
        sumSquares += (int64_t)sample * (int64_t)sample;
        dcSum += sample;
    }

    const uint32_t rms = (uint32_t)sqrt((double)sumSquares / max<size_t>(1, count));
    const int32_t dc = (int32_t)(dcSum / (int64_t)max<size_t>(1, count));
    const uint32_t now = millis();

    if (now - bootMs < CALIBRATION_MS) {
        calibrationRmsSum += rms;
        calibrationFrames++;
        calibratedNoiseFloor = calibrationFrames == 0
                                   ? 0
                                   : (uint32_t)(calibrationRmsSum / calibrationFrames);
    }

    if (now - lastStatusMs < STATUS_INTERVAL_MS) {
        return;
    }
    lastStatusMs = now;

    const uint32_t threshold = dynamicVoiceThreshold();
    const char* state = "SILENCE";
    if (rms >= VOICE_LOUD_THRESHOLD_RMS) {
        state = "LOUD";
    } else if (rms >= threshold) {
        state = "VOICE";
    }

    Serial.printf("[VoiceTest] state=%s rms=%lu peak=%ld dc=%ld noise=%lu threshold=%lu samples=%u\n",
                  state,
                  (unsigned long)rms,
                  (long)peak,
                  (long)dc,
                  (unsigned long)calibratedNoiseFloor,
                  (unsigned long)threshold,
                  (unsigned)count);
}
