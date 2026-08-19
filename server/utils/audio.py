"""WAV helpers. Convert to 16 kHz mono PCM, record from the mic, then drop buffers."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional

import numpy as np

TARGET_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2


class AudioError(Exception):
    pass


class MicrophoneError(AudioError):
    pass


def _as_int16_mono(frames: bytes, sample_width: int, channels: int) -> np.ndarray:
    if sample_width == 1:
        data = np.frombuffer(frames, dtype=np.uint8).astype(np.int16)
        data = (data - 128) * 256
    elif sample_width == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.int32)
    elif sample_width == 4:
        data = (np.frombuffer(frames, dtype=np.int32) // 65536).astype(np.int32)
    else:
        raise AudioError(f"Unsupported WAV sample width: {sample_width} bytes")

    if channels < 1:
        raise AudioError("WAV file has no audio channels")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return np.clip(data, -32768, 32767).astype(np.int16)


def resample_mono(samples: np.ndarray, src_rate: int, dst_rate: int = TARGET_RATE) -> np.ndarray:
    if src_rate <= 0:
        raise AudioError("Invalid sample rate")
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.int16, copy=False)
    duration = samples.size / src_rate
    n_out = max(1, int(round(duration * dst_rate)))
    x_old = np.linspace(0.0, 1.0, num=samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    resampled = np.interp(x_new, x_old, samples.astype(np.float32))
    return np.clip(resampled, -32768, 32767).astype(np.int16)


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as src:
        if src.getnframes() <= 0 or src.getframerate() <= 0:
            return 0.0
        return src.getnframes() / float(src.getframerate())


def load_wav_mono16k(path: Path) -> tuple[np.ndarray, int]:
    try:
        with wave.open(str(path), "rb") as src:
            channels = src.getnchannels()
            sample_width = src.getsampwidth()
            rate = src.getframerate()
            frames = src.readframes(src.getnframes())
    except wave.Error as exc:
        raise AudioError(f"Not a valid WAV file: {path.name}") from exc
    samples = _as_int16_mono(frames, sample_width, channels)
    samples = resample_mono(samples, rate, TARGET_RATE)
    return samples, TARGET_RATE


def write_wav_mono16k(path: Path, samples: np.ndarray, sample_rate: int = TARGET_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.ascontiguousarray(samples, dtype=np.int16)
    with wave.open(str(path), "wb") as dest:
        dest.setnchannels(TARGET_CHANNELS)
        dest.setsampwidth(TARGET_SAMPLE_WIDTH)
        dest.setframerate(sample_rate)
        dest.writeframes(pcm.tobytes())


def prepare_wav_for_whisper(
    source: Path,
    dest: Path,
    *,
    max_seconds: float,
) -> float:
    samples, rate = load_wav_mono16k(source)
    duration = samples.size / float(rate)
    if duration <= 0:
        raise AudioError("Audio file is empty")
    if duration > max_seconds:
        raise AudioError(
            f"Audio is {duration:.1f}s; maximum for short commands is {max_seconds:.0f}s"
        )
    write_wav_mono16k(dest, samples, rate)
    del samples
    return duration


def record_microphone(
    dest: Path,
    *,
    duration_seconds: float,
    sample_rate: int = TARGET_RATE,
    device: Optional[int] = None,
) -> float:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise MicrophoneError(
            "Microphone capture requires sounddevice. Install: pip install sounddevice"
        ) from exc

    frames = int(duration_seconds * sample_rate)
    if frames <= 0:
        raise MicrophoneError("Recording duration must be positive")
    try:
        recorded = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
        )
        sd.wait()
    except Exception as exc:  # PortAudio device errors
        raise MicrophoneError(f"Could not record from the microphone: {exc}") from exc

    samples = np.ascontiguousarray(recorded.reshape(-1), dtype=np.int16)
    write_wav_mono16k(dest, samples, sample_rate)
    del recorded
    del samples
    return duration_seconds
