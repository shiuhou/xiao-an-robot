#include <Arduino.h>
#include <driver/i2s.h>

#ifndef SPEAKER_I2S_BCLK
#define SPEAKER_I2S_BCLK 35
#endif

#ifndef SPEAKER_I2S_LRC
#define SPEAKER_I2S_LRC 36
#endif

#ifndef SPEAKER_I2S_DIN
#define SPEAKER_I2S_DIN 37
#endif

#ifndef SPEAKER_SAMPLE_RATE
#define SPEAKER_SAMPLE_RATE 16000
#endif

#ifndef SPEAKER_AMPLITUDE
#define SPEAKER_AMPLITUDE 4500
#endif

static constexpr i2s_port_t SPEAKER_I2S_PORT = I2S_NUM_1;
static constexpr size_t FRAMES_PER_BUFFER = 128;
static constexpr uint32_t STARTUP_DELAY_MS = 1500;

static int16_t stereoBuffer[FRAMES_PER_BUFFER * 2];

static bool installSpeakerI2S() {
    const i2s_config_t config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
        .sample_rate = SPEAKER_SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 6,
        .dma_buf_len = 256,
        .use_apll = false,
        .tx_desc_auto_clear = true,
        .fixed_mclk = 0,
        .mclk_multiple = I2S_MCLK_MULTIPLE_DEFAULT,
        .bits_per_chan = I2S_BITS_PER_CHAN_16BIT,
    };

    const i2s_pin_config_t pins = {
        .mck_io_num = I2S_PIN_NO_CHANGE,
        .bck_io_num = SPEAKER_I2S_BCLK,
        .ws_io_num = SPEAKER_I2S_LRC,
        .data_out_num = SPEAKER_I2S_DIN,
        .data_in_num = I2S_PIN_NO_CHANGE,
    };

    esp_err_t err = i2s_driver_install(SPEAKER_I2S_PORT, &config, 0, nullptr);
    if (err != ESP_OK) {
        Serial.printf("[SpeakerTest][ERR] i2s_driver_install failed: %d\n", err);
        return false;
    }

    err = i2s_set_pin(SPEAKER_I2S_PORT, &pins);
    if (err != ESP_OK) {
        Serial.printf("[SpeakerTest][ERR] i2s_set_pin failed: %d\n", err);
        i2s_driver_uninstall(SPEAKER_I2S_PORT);
        return false;
    }

    i2s_zero_dma_buffer(SPEAKER_I2S_PORT);
    return true;
}

static void writeSilence(uint32_t durationMs) {
    memset(stereoBuffer, 0, sizeof(stereoBuffer));
    const uint32_t totalFrames = (uint32_t)((uint64_t)SPEAKER_SAMPLE_RATE * durationMs / 1000);
    uint32_t framesWritten = 0;

    while (framesWritten < totalFrames) {
        const uint32_t framesThisWrite = min<uint32_t>(FRAMES_PER_BUFFER, totalFrames - framesWritten);
        size_t bytesWritten = 0;
        i2s_write(
            SPEAKER_I2S_PORT,
            stereoBuffer,
            framesThisWrite * 2 * sizeof(int16_t),
            &bytesWritten,
            portMAX_DELAY);
        framesWritten += framesThisWrite;
    }
}

static void playTone(uint32_t frequencyHz, uint32_t durationMs) {
    const uint32_t totalFrames = (uint32_t)((uint64_t)SPEAKER_SAMPLE_RATE * durationMs / 1000);
    uint32_t framesWritten = 0;
    uint32_t phase = 0;
    const uint32_t phaseStep = (uint32_t)(((uint64_t)frequencyHz << 32) / SPEAKER_SAMPLE_RATE);

    while (framesWritten < totalFrames) {
        const uint32_t framesThisWrite = min<uint32_t>(FRAMES_PER_BUFFER, totalFrames - framesWritten);

        for (uint32_t i = 0; i < framesThisWrite; ++i) {
            phase += phaseStep;
            const int16_t sample = (phase & 0x80000000UL) ? SPEAKER_AMPLITUDE : -SPEAKER_AMPLITUDE;
            stereoBuffer[i * 2] = sample;
            stereoBuffer[i * 2 + 1] = sample;
        }

        size_t bytesWritten = 0;
        i2s_write(
            SPEAKER_I2S_PORT,
            stereoBuffer,
            framesThisWrite * 2 * sizeof(int16_t),
            &bytesWritten,
            portMAX_DELAY);
        framesWritten += framesThisWrite;
    }
}

static void printWiring() {
    Serial.println();
    Serial.println("[SpeakerTest] MAX98357A wiring:");
    Serial.println("[SpeakerTest] VIN -> 5V or 3V3, GND -> common GND");
    Serial.printf("[SpeakerTest] BCLK -> GPIO%d, LRC/WS -> GPIO%d, DIN -> GPIO%d\n",
                  SPEAKER_I2S_BCLK,
                  SPEAKER_I2S_LRC,
                  SPEAKER_I2S_DIN);
    Serial.println("[SpeakerTest] SD -> VIN/3V3 enable, GAIN -> leave open or GND for lower gain");
    Serial.println("[SpeakerTest] Speaker connects only to the amp + and - outputs, not to ESP32 pins.");
}

void setup() {
    Serial.begin(115200);
    delay(STARTUP_DELAY_MS);

    Serial.println("[SpeakerTest] Xiao-An MAX98357A I2S speaker amp test");
    Serial.printf("[SpeakerTest] sample_rate=%d amplitude=%d\n",
                  SPEAKER_SAMPLE_RATE,
                  SPEAKER_AMPLITUDE);
    printWiring();

    if (!installSpeakerI2S()) {
        Serial.println("[SpeakerTest][ERR] Speaker I2S init failed. Check pin config, then reset.");
        while (true) {
            delay(1000);
        }
    }

    Serial.println("[SpeakerTest] Init OK. Playing short beep pattern every 3 seconds.");
}

void loop() {
    Serial.println("[SpeakerTest] beep 440Hz");
    playTone(440, 180);
    writeSilence(120);
    Serial.println("[SpeakerTest] beep 660Hz");
    playTone(660, 180);
    writeSilence(2600);
}
