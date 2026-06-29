"""TTS helpers for streaming robot speaker audio over WebSocket control."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import subprocess
import time
import uuid
import wave


@dataclass(frozen=True)
class TtsPcmStream:
    audio_id: str
    text_preview: str
    pcm: bytes
    sample_rate: int
    channels: int

    @property
    def duration_ms(self) -> int:
        bytes_per_frame = self.channels * 2
        if self.sample_rate <= 0 or bytes_per_frame <= 0:
            return 0
        return int(len(self.pcm) / bytes_per_frame / self.sample_rate * 1000)


def _read_pcm_s16le_wav(path: Path) -> tuple[bytes, int, int]:
    with wave.open(str(path), "rb") as wav:
        sample_width = wav.getsampwidth()
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        if sample_width != 2:
            raise RuntimeError(f"TTS WAV must be 16-bit PCM, got sample_width={sample_width}")
        if channels != 1:
            raise RuntimeError(f"TTS WAV must be mono, got channels={channels}")
        return wav.readframes(wav.getnframes()), sample_rate, channels


def limit_pcm_peak_s16le(pcm: bytes, target_peak: int = 900) -> bytes:
    if not pcm or target_peak <= 0:
        return pcm

    usable_len = len(pcm) - (len(pcm) % 2)
    if usable_len <= 0:
        return pcm

    samples = [
        int.from_bytes(pcm[index:index + 2], "little", signed=True)
        for index in range(0, usable_len, 2)
    ]
    peak = max((abs(sample) for sample in samples), default=0)
    if peak <= target_peak:
        return pcm

    scale = target_peak / peak
    limited = bytearray()
    for sample in samples:
        scaled = int(sample * scale)
        limited.extend(scaled.to_bytes(2, "little", signed=True))
    if usable_len < len(pcm):
        limited.extend(pcm[usable_len:])
    return bytes(limited)


def _run_windows_sapi(text_path: Path, wav_path: Path) -> None:
    script_path = wav_path.with_suffix(".ps1")
    script = r"""
param([string]$TextPath, [string]$WavPath)
Add-Type -AssemblyName System.Speech
$text = Get-Content -LiteralPath $TextPath -Raw -Encoding UTF8
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
  16000,
  [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
  [System.Speech.AudioFormat.AudioChannel]::Mono
)
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($text -match '[\u3400-\u9fff]') {
  $voice = $synth.GetInstalledVoices() |
    Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' } |
    Select-Object -First 1
  if ($voice -ne $null) {
    $synth.SelectVoice($voice.VoiceInfo.Name)
  }
}
$synth.SetOutputToWaveFile($WavPath, $format)
$synth.Speak($text)
$synth.Dispose()
"""
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-TextPath",
            str(text_path),
            "-WavPath",
            str(wav_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Windows SAPI TTS failed: {result.stderr.strip() or result.stdout.strip()}")


def _run_external_tts_command(text_path: Path, wav_path: Path) -> None:
    command_template = os.environ.get("XIAOAN_TTS_COMMAND", "").strip()
    if not command_template:
        raise RuntimeError("No TTS backend configured. Set XIAOAN_TTS_COMMAND on non-Windows hosts.")

    command = [
        part.format(text_file=str(text_path), wav_file=str(wav_path))
        for part in shlex.split(command_template)
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"External TTS command failed: {result.stderr.strip() or result.stdout.strip()}")


def synthesize_tts_pcm_stream(text: str, runtime_dir: Path | str = Path("runtime")) -> TtsPcmStream:
    text = (text or "").strip()
    if not text:
        raise RuntimeError("TTS text is empty")

    audio_id = f"tts-{uuid.uuid4().hex[:8]}"
    tts_dir = Path(runtime_dir) / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    text_path = tts_dir / f"{audio_id}-{stamp}.txt"
    wav_path = tts_dir / f"{audio_id}-{stamp}.wav"
    text_path.write_text(text, encoding="utf-8")

    if os.name == "nt":
        _run_windows_sapi(text_path, wav_path)
    else:
        _run_external_tts_command(text_path, wav_path)

    pcm, sample_rate, channels = _read_pcm_s16le_wav(wav_path)
    pcm = limit_pcm_peak_s16le(pcm)
    if not pcm:
        raise RuntimeError("TTS backend produced an empty PCM stream")
    return TtsPcmStream(
        audio_id=audio_id,
        text_preview=text,
        pcm=pcm,
        sample_rate=sample_rate,
        channels=channels,
    )
