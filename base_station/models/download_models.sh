#!/bin/bash
# download_models.sh - Download all required OpenVINO and ONNX models
# Author: 郑斯悦

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Downloading OpenVINO Model Zoo models..."
# Requires: pip install openvino-dev[onnx,pytorch]

# Face Emotion Recognition
# omz_downloader --name emotions-recognition-retail-0003 --output_dir .

# Head Pose Estimation
# omz_downloader --name head-pose-estimation-adas-0001 --output_dir .

echo "Downloading Silero VAD..."
# wget -O silero_vad.onnx https://github.com/snakers4/silero-vad/releases/download/v5.0/silero_vad.onnx

echo "Downloading Sherpa-ONNX Chinese ASR model..."
# wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2
# tar xf sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2
# mv sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23 sherpa-onnx-streaming-zipformer-zh

echo "Done. All model files should now be in base_station/models/"
