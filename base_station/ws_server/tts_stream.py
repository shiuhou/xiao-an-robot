"""TTS helpers for streaming robot speaker audio over WebSocket control."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid
import wave

DEFAULT_TTS_TARGET_PEAK = 500
TTS_COMMAND_ENV = "XIAOAN_TTS_COMMAND"
TTS_TARGET_PEAK_ENV = "XIAOAN_TTS_TARGET_PEAK"
TTS_VOICE_ENV = "XIAOAN_TTS_VOICE"
TTS_RATE_ENV = "XIAOAN_TTS_RATE"


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


def normalize_pcm_peak_s16le(pcm: bytes, target_peak: int = DEFAULT_TTS_TARGET_PEAK) -> bytes:
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
    if peak == 0:
        return pcm

    scale = target_peak / peak
    normalized = bytearray()
    for sample in samples:
        scaled = int(sample * scale)
        if scaled > 32767:
            scaled = 32767
        elif scaled < -32768:
            scaled = -32768
        normalized.extend(scaled.to_bytes(2, "little", signed=True))
    if usable_len < len(pcm):
        normalized.extend(pcm[usable_len:])
    return bytes(normalized)


def limit_pcm_peak_s16le(pcm: bytes, target_peak: int = DEFAULT_TTS_TARGET_PEAK) -> bytes:
    return normalize_pcm_peak_s16le(pcm, target_peak=target_peak)


def tts_target_peak_from_env() -> int:
    raw = os.environ.get(TTS_TARGET_PEAK_ENV, "").strip()
    if not raw:
        return DEFAULT_TTS_TARGET_PEAK
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTS_TARGET_PEAK
    return max(1, min(value, 32767))


def default_edge_tts_script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "runtime" / "tts_probe" / "edge_tts_to_wav.py"


def default_edge_tts_command_template() -> str:
    script_path = default_edge_tts_script_path()
    return (
        f"{shlex.quote(sys.executable)} "
        f"{shlex.quote(str(script_path))} "
        "{text_file} {wav_file}"
    )


def tts_command_template_from_env() -> str:
    command_template = os.environ.get(TTS_COMMAND_ENV, "").strip()
    if command_template:
        return command_template
    if default_edge_tts_script_path().exists():
        return default_edge_tts_command_template()
    return ""


def external_tts_backend_configured() -> bool:
    return bool(tts_command_template_from_env())


def windows_sapi_script() -> str:
    return r"""
param([string]$TextPath, [string]$WavPath)
Add-Type -AssemblyName System.Speech
$text = Get-Content -LiteralPath $TextPath -Raw -Encoding UTF8
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
  16000,
  [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
  [System.Speech.AudioFormat.AudioChannel]::Mono
)
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$requestedVoice = [Environment]::GetEnvironmentVariable('XIAOAN_TTS_VOICE')
$requestedRate = [Environment]::GetEnvironmentVariable('XIAOAN_TTS_RATE')
if ($requestedRate) {
  $parsedRate = 0
  if ([int]::TryParse($requestedRate, [ref]$parsedRate)) {
    if ($parsedRate -lt -10) { $parsedRate = -10 }
    if ($parsedRate -gt 10) { $parsedRate = 10 }
    $synth.Rate = $parsedRate
  }
}
$voiceSelected = $false
if ($requestedVoice) {
  $voice = $synth.GetInstalledVoices() |
    Where-Object { $_.Enabled -and $_.VoiceInfo.Name -eq $requestedVoice } |
    Select-Object -First 1
  if ($voice -ne $null) {
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $voiceSelected = $true
  }
}
if ($text -match '[\u3400-\u9fff]') {
  $selectedVoice = $null
  if (-not $voiceSelected) {
    foreach ($culture in @('zh-CN', 'zh-TW', 'zh-HK')) {
      $selectedVoice = $synth.GetInstalledVoices() |
        Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq $culture } |
        Select-Object -First 1
      if ($selectedVoice -ne $null) {
        break
      }
    }
  }
  if ($selectedVoice -ne $null) {
    $synth.SelectVoice($selectedVoice.VoiceInfo.Name)
  }
}
$synth.SetOutputToWaveFile($WavPath, $format)
$synth.Speak($text)
$synth.Dispose()
"""


def _run_windows_sapi(text_path: Path, wav_path: Path) -> None:
    script_path = wav_path.with_suffix(".ps1")
    script = windows_sapi_script()
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
    command_template = tts_command_template_from_env()
    if not command_template:
        raise RuntimeError(
            "No TTS backend configured. Set XIAOAN_TTS_COMMAND or create runtime/tts_probe/edge_tts_to_wav.py."
        )

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
    pcm = normalize_pcm_peak_s16le(pcm, target_peak=tts_target_peak_from_env())
    if not pcm:
        raise RuntimeError("TTS backend produced an empty PCM stream")
    return TtsPcmStream(
        audio_id=audio_id,
        text_preview=text,
        pcm=pcm,
        sample_rate=sample_rate,
        channels=channels,
    )
