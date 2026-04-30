#include "mic_stream.h"

void MicStream::begin() {
    // TODO: configure I2S driver for INMP441 microphone
    // TODO: set sample rate 16000 Hz, 16-bit mono
}

void MicStream::streamLoop() {
    // TODO: read I2S DMA buffer
    // TODO: if VAD detects speech, send PCM chunk via WebSocket /audio channel
}

bool MicStream::isActive() {
    return _active;
}
