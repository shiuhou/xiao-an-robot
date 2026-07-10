"""TTS helpers for streaming robot speaker audio over WebSocket control."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import uuid
import wave

DEFAULT_TTS_TARGET_PEAK = 500
TTS_SAMPLE_RATE = 16000
TTS_CHANNELS = 1
TTS_SAMPLE_WIDTH_BYTES = 2
TTS_CACHE_DIR_NAME = "tts_cache"
TTS_COMMAND_ENV = "XIAOAN_TTS_COMMAND"
TTS_TARGET_PEAK_ENV = "XIAOAN_TTS_TARGET_PEAK"
TTS_VOICE_ENV = "XIAOAN_TTS_VOICE"
TTS_RATE_ENV = "XIAOAN_TTS_RATE"
EDGE_TTS_VOICE_ENV = "XIAOAN_EDGE_TTS_VOICE"
EDGE_TTS_RATE_ENV = "XIAOAN_EDGE_TTS_RATE"
EDGE_TTS_VOLUME_ENV = "XIAOAN_EDGE_TTS_VOLUME"
DEFAULT_EDGE_TTS_VOICE = "zh-CN-XiaoxiaoNeural"


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
        if sample_width != TTS_SAMPLE_WIDTH_BYTES:
            raise RuntimeError(f"TTS WAV must be 16-bit PCM, got sample_width={sample_width}")
        if channels != TTS_CHANNELS:
            raise RuntimeError(f"TTS WAV must be mono, got channels={channels}")
        if sample_rate != TTS_SAMPLE_RATE:
            raise RuntimeError(f"TTS WAV must be 16000 Hz, got sample_rate={sample_rate}")
        return wav.readframes(wav.getnframes()), sample_rate, channels


def _cache_identity(text: str) -> str:
    command_template = tts_command_template_from_env()
    return "\0".join([
        os.name,
        command_template,
        os.environ.get(TTS_VOICE_ENV, ""),
        os.environ.get(TTS_RATE_ENV, ""),
        os.environ.get(EDGE_TTS_VOICE_ENV, DEFAULT_EDGE_TTS_VOICE),
        os.environ.get(EDGE_TTS_RATE_ENV, "+0%"),
        os.environ.get(EDGE_TTS_VOLUME_ENV, "+0%"),
        text,
    ])


def _tts_cache_path(runtime_dir: Path, text: str) -> Path:
    digest = hashlib.sha256(_cache_identity(text).encode("utf-8")).hexdigest()
    return runtime_dir / TTS_CACHE_DIR_NAME / f"{digest}.wav"


def tts_cache_path_for_text(text: str, runtime_dir: Path | str = Path("runtime")) -> Path:
    return _tts_cache_path(Path(runtime_dir), (text or "").strip())


def _tts_robot_pcm_cache_identity(text: str, target_peak: int) -> str:
    return "\0".join([
        _cache_identity(text),
        "raw_pcm_s16le",
        str(TTS_SAMPLE_RATE),
        str(TTS_CHANNELS),
        str(TTS_SAMPLE_WIDTH_BYTES),
        str(target_peak),
    ])


def _tts_robot_pcm_cache_path(runtime_dir: Path, text: str, *, target_peak: int) -> Path:
    digest = hashlib.sha256(_tts_robot_pcm_cache_identity(text, target_peak).encode("utf-8")).hexdigest()
    return runtime_dir / TTS_CACHE_DIR_NAME / f"{digest}.pcm"


def tts_robot_pcm_cache_path_for_text(
    text: str,
    runtime_dir: Path | str = Path("runtime"),
    *,
    target_peak: int | None = None,
) -> Path:
    peak = tts_target_peak_from_env() if target_peak is None else max(1, min(int(target_peak), 32767))
    return _tts_robot_pcm_cache_path(Path(runtime_dir), (text or "").strip(), target_peak=peak)


def _copy_wav_to_cache(source: Path, cache_path: Path) -> None:
    if not source.exists() or source.stat().st_size <= 0:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".wav.tmp")
    shutil.copyfile(source, tmp_path)
    os.replace(tmp_path, cache_path)


def _read_robot_pcm_cache(path: Path) -> bytes | None:
    try:
        pcm = path.read_bytes()
    except OSError:
        return None
    if not pcm or len(pcm) % TTS_SAMPLE_WIDTH_BYTES:
        return None
    return pcm


def _write_robot_pcm_cache(path: Path, pcm: bytes) -> None:
    if not pcm or len(pcm) % TTS_SAMPLE_WIDTH_BYTES:
        raise RuntimeError("robot PCM cache must be non-empty raw pcm_s16le")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".pcm.tmp")
    tmp_path.write_bytes(pcm)
    os.replace(tmp_path, path)


def _latest_legacy_tts_wav_for_text(runtime_dir: Path, text: str) -> Path | None:
    tts_dir = runtime_dir / "tts"
    try:
        text_files = sorted(
            tts_dir.glob("*.txt"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None

    for text_path in text_files:
        try:
            if text_path.read_text(encoding="utf-8").strip() != text:
                continue
            wav_path = text_path.with_suffix(".wav")
            if wav_path.exists() and wav_path.stat().st_size > 0:
                return wav_path
        except OSError:
            continue
    return None


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


def tts_backend_runtime_settings() -> dict[str, object]:
    command_template = tts_command_template_from_env()
    default_edge_script = default_edge_tts_script_path()
    if os.name == "nt":
        backend = "windows_sapi"
        voice = os.environ.get(TTS_VOICE_ENV, "")
        rate = os.environ.get(TTS_RATE_ENV, "") or "0"
        volume = ""
    elif command_template == default_edge_tts_command_template():
        backend = "edge_tts_to_wav.py"
        voice = os.environ.get(EDGE_TTS_VOICE_ENV, DEFAULT_EDGE_TTS_VOICE)
        rate = os.environ.get(EDGE_TTS_RATE_ENV, "+0%")
        volume = os.environ.get(EDGE_TTS_VOLUME_ENV, "+0%")
    elif command_template:
        backend = "external_command"
        voice = os.environ.get(TTS_VOICE_ENV, "")
        rate = os.environ.get(TTS_RATE_ENV, "")
        volume = ""
    else:
        backend = "unconfigured"
        voice = ""
        rate = ""
        volume = ""
    return {
        "backend": backend,
        "command_configured": bool(command_template),
        "command_template": command_template,
        "default_edge_script": str(default_edge_script),
        "voice": voice,
        "rate": rate,
        "volume": volume,
        "target_peak": tts_target_peak_from_env(),
        "pcm_format": "pcm_s16le",
        "sample_rate": TTS_SAMPLE_RATE,
        "channels": TTS_CHANNELS,
        "sample_width_bytes": TTS_SAMPLE_WIDTH_BYTES,
        "cache_payload": "robot_ready_raw_pcm_s16le",
    }


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
    runtime_path = Path(runtime_dir)
    tts_dir = runtime_path / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    text_path = tts_dir / f"{audio_id}-{stamp}.txt"
    wav_path = tts_dir / f"{audio_id}-{stamp}.wav"
    cache_path = _tts_cache_path(runtime_path, text)
    target_peak = tts_target_peak_from_env()
    pcm_cache_path = _tts_robot_pcm_cache_path(runtime_path, text, target_peak=target_peak)
    text_path.write_text(text, encoding="utf-8")

    cached_pcm = _read_robot_pcm_cache(pcm_cache_path)
    if cached_pcm is not None:
        return TtsPcmStream(
            audio_id=audio_id,
            text_preview=text,
            pcm=cached_pcm,
            sample_rate=TTS_SAMPLE_RATE,
            channels=TTS_CHANNELS,
        )

    source_wav_path = wav_path
    if cache_path.exists() and cache_path.stat().st_size > 0:
        source_wav_path = cache_path
    else:
        try:
            if os.name == "nt":
                _run_windows_sapi(text_path, wav_path)
            else:
                _run_external_tts_command(text_path, wav_path)
            _copy_wav_to_cache(wav_path, cache_path)
        except RuntimeError:
            legacy_wav = _latest_legacy_tts_wav_for_text(runtime_path, text)
            if legacy_wav is None:
                raise
            _copy_wav_to_cache(legacy_wav, cache_path)
            source_wav_path = legacy_wav

    pcm, sample_rate, channels = _read_pcm_s16le_wav(source_wav_path)
    pcm = normalize_pcm_peak_s16le(pcm, target_peak=target_peak)
    if not pcm:
        raise RuntimeError("TTS backend produced an empty PCM stream")
    _write_robot_pcm_cache(pcm_cache_path, pcm)
    return TtsPcmStream(
        audio_id=audio_id,
        text_preview=text,
        pcm=pcm,
        sample_rate=sample_rate,
        channels=channels,
    )
